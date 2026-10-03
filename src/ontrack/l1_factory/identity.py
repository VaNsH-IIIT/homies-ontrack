"""Identity resolution: one golden_id per person across the five source systems (owner: P1).

Nodes are source keys:  crm:<crm_customer_id>, card:<src_customer_ref>, loan:<src_customer_ref>,
cif:<10-digit CIF>  (deposits and the bureau share the core-banking CIF, so they are one node).

Edges (each with a match method and confidence):
  tier 1 (bridges, ~deterministic)
    crm_duplicate   customers.duplicate_of_crm_id                          0.99
    national_id     same customers.national_id_hash                        0.99
    case_account    CRM id -> account in collections_cases.account_ids,
                    contact_history and agent_notes -> account's own key   0.98
    pad_link        loan_accounts.pad_source_account -> same-bank deposit  0.95
  tier 2 (strong deterministic on standardised fields)
    name_dob_postal same surname + DOB + postal code, compatible initial    0.97
    name_dob_phone  same surname + DOB + unmasked phone, compatible initial 0.97
Joint holders and co-borrowers are never edges (related parties, not the same person).
Probabilistic matching (Splink) for the remaining records is phase 2.

Connected components (union-find) give the golden_id, with a conflict guard: two clusters whose CRM
records share no date of birth are never joined (refused links logged in silver.identity_refused); match_confidence is the confidence of the
edge that attached the key (1.0 for the anchor key of the cluster).
"""
from ontrack.db import connect

# Values shared by too many people are not evidence of identity.
SHARED_VALUE_LIMIT = 5

EDGES_SQL = {
    "crm_duplicate": """
        SELECT 'crm:' || crm_customer_id AS a, 'crm:' || duplicate_of_crm_id AS b, 0.99 AS conf
        FROM silver.crm WHERE duplicate_of_crm_id IS NOT NULL
    """,
    "national_id": """
        WITH h AS (SELECT national_id_hash, crm_customer_id FROM silver.crm WHERE national_id_hash IS NOT NULL),
             ok AS (SELECT national_id_hash FROM h GROUP BY 1 HAVING count(*) BETWEEN 2 AND 3)
        SELECT 'crm:' || min(crm_customer_id) AS a, 'crm:' || max(crm_customer_id) AS b, 0.99 AS conf
        FROM h JOIN ok USING (national_id_hash) GROUP BY national_id_hash
    """,
    "case_account": """
        WITH crm_acct AS (
            SELECT DISTINCT coll_customer_ref AS crm_id, trim(unnest(
                CASE WHEN account_ids LIKE '[%' THEN from_json(account_ids, '["VARCHAR"]')
                     ELSE string_split(account_ids, ';') END)) AS account_id
            FROM bronze.collections_cases WHERE account_ids IS NOT NULL
            UNION
            SELECT DISTINCT crm_customer_id, account_id FROM bronze.contact_history
            WHERE crm_customer_id IS NOT NULL AND account_id IS NOT NULL
            UNION
            SELECT DISTINCT crm_customer_id, account_id FROM bronze.agent_notes
            WHERE crm_customer_id IS NOT NULL AND account_id IS NOT NULL
        ),
        acct_key AS (
            SELECT card_account_id AS account_id, 'card:' || src_customer_ref AS node FROM silver.card_accounts
            UNION ALL SELECT loan_id, 'loan:' || src_customer_ref FROM silver.loan_accounts
            UNION ALL SELECT deposit_account_id, 'cif:' || src_customer_ref FROM silver.deposit_accounts
        )
        SELECT DISTINCT 'crm:' || crm_id AS a, node AS b, 0.98 AS conf
        FROM crm_acct JOIN acct_key USING (account_id)
    """,
    "pad_link": """
        SELECT DISTINCT 'loan:' || l.src_customer_ref AS a, 'cif:' || d.src_customer_ref AS b, 0.95 AS conf
        FROM silver.loan_accounts l JOIN silver.deposit_accounts d ON d.deposit_account_id = l.pad_source_account
        WHERE l.pad_source_account <> 'EXTERNAL'
    """,
}

PARTIES = {"card": "silver.card_parties", "loan": "silver.loan_parties",
           "cif": "silver.deposit_parties", "cif_bureau": "silver.bureau_parties"}


def tier2_sql(prefix: str, table: str, field: str, method: str) -> str:
    node_prefix = "cif" if prefix.startswith("cif") else prefix
    return f"""
        WITH crm AS (
            SELECT crm_customer_id, regexp_replace(surname_std, '[^A-Z]', '', 'g') AS surname_std, given_std, dob, {field} AS v FROM silver.crm
            WHERE surname_std IS NOT NULL AND dob IS NOT NULL AND {field} IS NOT NULL
        ),
        src AS (
            SELECT source_key, regexp_replace(surname_std, '[^A-Z]', '', 'g') AS surname_std, given_std, dob, {field} AS v FROM {table}
            WHERE surname_std IS NOT NULL AND dob IS NOT NULL AND {field} IS NOT NULL AND {field} NOT LIKE '%x%'
        ),
        common AS (SELECT v FROM crm GROUP BY v HAVING count(DISTINCT surname_std || dob) <= {SHARED_VALUE_LIMIT})
        SELECT DISTINCT 'crm:' || c.crm_customer_id AS a, '{node_prefix}:' || s.source_key AS b, 0.97 AS conf
        FROM src s JOIN crm c ON c.surname_std = s.surname_std AND c.dob = s.dob AND c.v = s.v
        JOIN common ON common.v = c.v
        WHERE s.given_std IS NULL OR c.given_std IS NULL OR left(s.given_std, 1) = left(c.given_std, 1)
    """


def all_nodes_sql() -> str:
    return """
        SELECT 'crm:' || crm_customer_id AS node FROM silver.crm
        UNION SELECT 'card:' || source_key FROM silver.card_parties
        UNION SELECT 'loan:' || source_key FROM silver.loan_parties
        UNION SELECT 'cif:' || source_key FROM silver.deposit_parties
        UNION SELECT 'cif:' || source_key FROM silver.bureau_parties
    """


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        root = x
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while self.parent.get(x, x) != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if rb < ra:
                ra, rb = rb, ra
            self.parent[rb] = ra


def main() -> None:
    con = connect()
    con.execute("CREATE OR REPLACE TABLE silver.identity_edges (a VARCHAR, b VARCHAR, conf DOUBLE, method VARCHAR)")
    for method, sql in EDGES_SQL.items():
        con.execute(f"INSERT INTO silver.identity_edges SELECT a, b, conf, '{method}' FROM ({sql})")
    for prefix, table in PARTIES.items():
        for field, method in (("postal6", "name_dob_postal"), ("phone10", "name_dob_phone")):
            if prefix == "cif_bureau" and field == "phone10":
                continue
            con.execute(f"INSERT INTO silver.identity_edges SELECT a, b, conf, '{method}' FROM ({tier2_sql(prefix, table, field, method)})")
    for m, n in con.execute("SELECT method, count(*) FROM silver.identity_edges GROUP BY 1 ORDER BY 2 DESC").fetchall():
        print(f"  edges {m:16s} {n:>10,d}", flush=True)

    uf = UnionFind()
    nodes = [r[0] for r in con.execute(all_nodes_sql()).fetchall()]
    for n in nodes:
        uf.parent.setdefault(n, n)
    # Conflict guard: never join two clusters whose CRM records share no date of birth
    # (two different people). CRM's own duplicate flag is the bank's explicit statement, so it is exempt.
    dobs = {f"crm:{cid}": {d} for cid, d in con.execute(
        "SELECT crm_customer_id, dob FROM silver.crm WHERE dob IS NOT NULL").fetchall()}
    best, refused = {}, []
    # Strongest edges first, so each key's best evidence is recorded.
    for a, b, conf, method in con.execute(
            "SELECT a, b, conf, method FROM silver.identity_edges ORDER BY conf DESC, method").fetchall():
        uf.parent.setdefault(a, a)
        uf.parent.setdefault(b, b)
        ra, rb = uf.find(a), uf.find(b)
        if ra != rb:
            da, db = dobs.get(ra, set()), dobs.get(rb, set())
            if method != "crm_duplicate" and da and db and not (da & db):
                refused.append((a, b, conf, method))
                continue
            uf.union(ra, rb)
            root = uf.find(ra)
            dobs[root] = da | db
        for node in (a, b):
            if node not in best or conf > best[node][0]:
                best[node] = (conf, method)
    con.execute("CREATE OR REPLACE TABLE silver.identity_refused (a VARCHAR, b VARCHAR, conf DOUBLE, method VARCHAR)")
    if refused:
        import pyarrow as pa
        cols = list(zip(*refused))
        con.register("refused_arrow", pa.table({"a": cols[0], "b": cols[1], "conf": cols[2], "method": cols[3]}))
        con.execute("INSERT INTO silver.identity_refused SELECT * FROM refused_arrow")
        con.unregister("refused_arrow")
    print(f"  conflict guard refused {len(refused):,d} links between clusters with different dates of birth", flush=True)

    # golden_id per component, numbered by the component's smallest key for stability.
    roots = {}
    rows = []
    for node in sorted(uf.parent):
        root = uf.find(node)
        if root not in roots:
            roots[root] = f"G-{len(roots) + 1:07d}"
        system, key = node.split(":", 1)
        conf, method = best.get(node, (1.0, "singleton"))
        rows.append((roots[root], {"crm": "crm", "card": "cards", "loan": "loans", "cif": "core_banking"}[system],
                     key, method, conf))

    import pyarrow as pa  # bulk insert: row-by-row inserts of millions of keys are far too slow
    cols = list(zip(*rows))
    xref = pa.table({"golden_id": cols[0], "source_system": cols[1], "source_key": cols[2],
                     "match_method": cols[3], "match_confidence": pa.array(cols[4], pa.float64())})
    con.register("xref_arrow", xref)
    con.execute("CREATE OR REPLACE TABLE gold.customer_xref AS SELECT * FROM xref_arrow")
    con.unregister("xref_arrow")
    sizes = con.execute("""SELECT count(*) AS clusters, max(n) AS largest,
                                  count(*) FILTER (WHERE n = 1) AS singletons
                           FROM (SELECT golden_id, count(*) n FROM gold.customer_xref GROUP BY 1)""").fetchone()
    print(f"gold.customer_xref: {len(rows):,d} keys -> {sizes[0]:,d} golden_ids "
          f"(largest cluster {sizes[1]} keys, {sizes[2]:,d} singletons)", flush=True)
    con.close()


if __name__ == "__main__":
    main()
