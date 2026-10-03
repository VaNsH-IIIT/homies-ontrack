"""Tier 3 identity resolution: probabilistic matching with Splink (owner: P1).

    python -m ontrack.l1_factory.probabilistic      (run by build.py between two identity passes)

Compares the source keys still unlinked after tiers 1-2 (cards, loans, core-banking CIFs) against
every CRM person, on surname (Jaro-Winkler), given-name initial, date of birth (allowing typos and
day/month swaps), postal code and phone. Fellegi-Sunter weights are learnt without labels (EM).

Decision:   match probability >= 0.95  -> link (method 'splink', confidence = probability)
            0.80 <= p < 0.95           -> gold.match_review_queue for a data steward (not merged until the
                                          steward approves it on the Match review page; applied next build)
Validation: 5,000 keys already linked by tier-1 case-to-account bridges are matched blind as well;
            precision and recall on them are written to silver.splink_validation (free ground truth).
"""
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

from ontrack import config
from ontrack.db import connect

AUTO_LINK = 0.95
REVIEW = 0.80
HOLDOUT = 5000
STEWARD_DB = config.WORK_DIR / "decisions.duckdb"  # written by the app (Match review page)
STEWARD_CONF = 0.97  # a human-verified link counts like a deterministic tier-2 match

PARTY = """
    SELECT 'card:' || source_key AS uid, * FROM silver.card_parties
    UNION ALL SELECT 'loan:' || source_key, * FROM silver.loan_parties
    UNION ALL SELECT 'cif:' || source_key, * FROM silver.deposit_parties
    UNION ALL SELECT 'cif:' || source_key, * FROM silver.bureau_parties
        WHERE source_key NOT IN (SELECT source_key FROM silver.deposit_parties)
"""


def features(select_from: str) -> str:
    return f"""
        SELECT uid,
               nullif(regexp_replace(surname_std, '[^A-Z]', '', 'g'), '') AS surname_key,
               nullif(left(regexp_replace(given_std, '[^A-Z]', '', 'g'), 1), '') AS given_initial,
               dob,
               CASE WHEN phone10 LIKE '%x%' THEN NULL ELSE phone10 END AS phone10,
               postal6,
               left(postal6, 3) AS fsa
        FROM ({select_from})
    """


def mask(col: str) -> str:
    """Initial plus one dot per remaining letter, e.g. VAUGHN -> V•••••."""
    return f"CASE WHEN {col} IS NULL THEN NULL ELSE left({col}, 1) || repeat('•', length({col}) - 1) END"


def apply_steward_decisions(con) -> None:
    """Feed the data steward's decisions (Match review page) back in: the latest decision per pair wins.
    Approved pairs become links (method 'steward_approved'); rejected pairs are never linked."""
    if not STEWARD_DB.exists():
        return
    try:
        con.execute(f"ATTACH '{STEWARD_DB.as_posix()}' AS dec (READ_ONLY)")
    except Exception as e:  # the app may hold the file for a moment; decisions apply on the next build
        print(f"  steward decisions not read ({e.__class__.__name__}); they apply on the next build", flush=True)
        return
    try:
        if not con.execute("SELECT count(*) FROM information_schema.tables "
                           "WHERE table_catalog = 'dec' AND table_name = 'steward_log'").fetchone()[0]:
            return
        con.execute("""
            UPDATE gold.match_review_queue q SET steward_status = d.decision
            FROM (SELECT * FROM dec.steward_log
                  QUALIFY row_number() OVER (PARTITION BY source_system, source_key, candidate_crm_customer_id
                                             ORDER BY ts DESC) = 1) d
            WHERE q.source_system = d.source_system AND q.source_key = d.source_key
              AND q.candidate_crm_customer_id = d.candidate_crm_customer_id""")
        con.execute(f"""
            INSERT INTO silver.splink_edges
            SELECT 'crm:' || candidate_crm_customer_id, source_system || ':' || source_key, {STEWARD_CONF}, 'steward_approved'
            FROM gold.match_review_queue WHERE steward_status = 'approved'""")
        counts = dict(con.execute("SELECT steward_status, count(*) FROM gold.match_review_queue GROUP BY 1").fetchall())
        print(f"  steward decisions applied: {counts.get('approved', 0):,d} approved (linked), "
              f"{counts.get('rejected', 0):,d} rejected, {counts.get('pending', 0):,d} pending", flush=True)
    finally:
        con.execute("DETACH dec")


def main() -> None:
    con = connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS splink")
    node_of = "CASE x.source_system WHEN 'cards' THEN 'card:' WHEN 'loans' THEN 'loan:' ELSE 'cif:' END || x.source_key"
    con.execute(f"""
        CREATE OR REPLACE TABLE splink.unlinked AS
        SELECT {node_of} AS uid, FALSE AS is_holdout
        FROM gold.customer_xref x
        JOIN (SELECT golden_id FROM gold.customer_xref GROUP BY 1 HAVING count(*) = 1) s USING (golden_id)
        WHERE x.source_system <> 'crm'
    """)
    # Holdout: keys whose owner is known from a tier-1 bridge, matched blind to measure accuracy.
    con.execute(f"""
        INSERT INTO splink.unlinked
        SELECT uid, TRUE FROM (
            SELECT {node_of} AS uid FROM gold.customer_xref x
            WHERE x.match_method = 'case_account' AND x.source_system <> 'crm'
        ) USING SAMPLE {HOLDOUT} ROWS (reservoir, 42)
    """)
    crm_src = "SELECT 'crm:' || crm_customer_id AS uid, * FROM silver.crm"
    con.execute(f"CREATE OR REPLACE TABLE splink.left_crm AS {features(crm_src)}")
    right_src = f"SELECT p.* FROM ({PARTY}) p JOIN splink.unlinked u USING (uid)"
    con.execute(f"CREATE OR REPLACE TABLE splink.right_src AS {features(right_src)}")
    n_right = con.execute("SELECT count(*) FROM splink.right_src").fetchone()[0]
    print(f"  splink: {n_right:,d} source keys to match against CRM", flush=True)

    settings = SettingsCreator(
        link_type="link_only",
        unique_id_column_name="uid",
        comparisons=[
            cl.JaroWinklerAtThresholds("surname_key", [0.95, 0.88]),
            cl.ExactMatch("given_initial"),
            cl.DateOfBirthComparison("dob", input_is_string=False),
            cl.LevenshteinAtThresholds("postal6", [1, 2]),
            cl.ExactMatch("phone10"),
        ],
        blocking_rules_to_generate_predictions=[
            block_on("dob"),
            block_on("postal6"),
            block_on("surname_key", "fsa"),
            block_on("phone10"),
        ],
        retain_intermediate_calculation_columns=True,
    )
    db_api = DuckDBAPI(connection=con, output_schema="splink")
    left = db_api.register(con.table("splink.left_crm").fetch_arrow_table(), table_name="splink_left_crm")
    right = db_api.register(con.table("splink.right_src").fetch_arrow_table(), table_name="splink_right_src")
    linker = Linker([left, right], settings)
    linker.training.estimate_probability_two_random_records_match([block_on("surname_key", "dob")], recall=0.8)
    linker.training.estimate_u_using_random_sampling(max_pairs=2e6)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("dob"))
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("postal6"))
    preds = linker.inference.predict(threshold_match_probability=REVIEW)

    # Best CRM candidate per source key.
    con.execute(f"""
        CREATE OR REPLACE TABLE splink.best AS
        SELECT p.uid_r AS uid, p.uid_l AS crm_uid, p.match_probability, p.match_weight
        FROM {preds.physical_name} p
        QUALIFY row_number() OVER (PARTITION BY p.uid_r ORDER BY p.match_probability DESC) = 1
    """)

    # Validation on the holdout: is the best CRM candidate in the key's known golden cluster?
    con.execute(f"""
        CREATE OR REPLACE TABLE silver.splink_validation AS
        WITH truth AS (
            SELECT {node_of} AS uid, x.golden_id FROM gold.customer_xref x WHERE x.source_system <> 'crm'
        ),
        crm_gid AS (SELECT 'crm:' || source_key AS crm_uid, golden_id FROM gold.customer_xref WHERE source_system = 'crm'),
        h AS (
            SELECT u.uid, b.match_probability, (c.golden_id = t.golden_id) AS correct
            FROM splink.unlinked u JOIN truth t USING (uid)
            LEFT JOIN splink.best b USING (uid) LEFT JOIN crm_gid c ON c.crm_uid = b.crm_uid
            WHERE u.is_holdout
        )
        SELECT count(*) AS holdout_keys,
               count(*) FILTER (WHERE match_probability >= {AUTO_LINK}) AS auto_linked,
               count(*) FILTER (WHERE match_probability >= {AUTO_LINK} AND correct) AS auto_linked_correct,
               round(count(*) FILTER (WHERE match_probability >= {AUTO_LINK} AND correct)
                     / nullif(count(*) FILTER (WHERE match_probability >= {AUTO_LINK}), 0), 4) AS precision,
               round(count(*) FILTER (WHERE match_probability >= {AUTO_LINK} AND correct) / count(*), 4) AS recall
        FROM h
    """)
    v = con.execute("SELECT * FROM silver.splink_validation").fetchone()
    print(f"  validation on {v[0]:,d} known keys: precision {v[3]}, recall {v[4]}", flush=True)

    # Edges for auto-links (holdout keys excluded: they are already linked) and the steward queue.
    con.execute(f"""
        CREATE OR REPLACE TABLE silver.splink_edges AS
        SELECT b.crm_uid AS a, b.uid AS b, round(b.match_probability, 4) AS conf, 'splink' AS method
        FROM splink.best b JOIN splink.unlinked u USING (uid)
        WHERE NOT u.is_holdout AND b.match_probability >= {AUTO_LINK}
    """)
    # Evidence for the steward, per field. Values are masked (initial, birth year, postal FSA): gold holds no PII.
    con.execute(f"""
        CREATE OR REPLACE TABLE gold.match_review_queue AS
        SELECT split_part(b.uid, ':', 1) AS source_system, split_part(b.uid, ':', 2) AS source_key,
               split_part(b.crm_uid, ':', 2) AS candidate_crm_customer_id,
               round(b.match_probability, 4) AS match_probability, round(b.match_weight, 2) AS match_weight,
               {mask('l.surname_key')} AS crm_surname_masked, {mask('r.surname_key')} AS source_surname_masked,
               round(jaro_winkler_similarity(l.surname_key, r.surname_key), 3) AS surname_similarity,
               l.given_initial = r.given_initial AS given_initial_match,
               CASE WHEN l.dob IS NULL OR r.dob IS NULL THEN 'missing'
                    WHEN l.dob = r.dob THEN 'exact'
                    WHEN year(l.dob) = year(r.dob) AND month(l.dob) = day(r.dob) AND day(l.dob) = month(r.dob)
                         THEN 'day/month swapped'
                    WHEN year(l.dob) = year(r.dob) THEN 'same year only'
                    ELSE 'differs' END AS dob_check,
               levenshtein(l.postal6, r.postal6) AS postal_edit_distance,
               l.fsa AS crm_postal_fsa, r.fsa AS source_postal_fsa,
               l.phone10 = r.phone10 AS phone_match,
               'pending' AS steward_status
        FROM splink.best b JOIN splink.unlinked u USING (uid)
        LEFT JOIN splink.left_crm l ON l.uid = b.crm_uid
        LEFT JOIN splink.right_src r ON r.uid = b.uid
        WHERE NOT u.is_holdout AND b.match_probability >= {REVIEW} AND b.match_probability < {AUTO_LINK}
    """)
    apply_steward_decisions(con)
    auto = con.execute("SELECT count(*) FROM silver.splink_edges").fetchone()[0]
    review = con.execute("SELECT count(*) FROM gold.match_review_queue").fetchone()[0]
    print(f"  splink: {auto:,d} keys auto-linked (>= {AUTO_LINK}), {review:,d} sent to the steward queue", flush=True)
    con.execute("DROP SCHEMA splink CASCADE")
    con.close()


if __name__ == "__main__":
    main()
