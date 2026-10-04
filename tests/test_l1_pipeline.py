"""Layer 1 end to end on a tiny hand-made book: identity edges -> identity.main -> gold.main -> the real data
contract -> the DQ report (owner of the code: P1; tests by P3, K20). No dataset needed.

People in the book (silver tables are written directly, in the shape silver.STEPS produces):
  Alice  crm 100 + its CRM duplicate 101 (later update, cease request, no SMS consent), card C1 (case account, JSON
         list), loan L1 (case account, ';' list), deposit D1 (loan L1's pre-authorised debit), crm 999 (a case whose
         CRM record is missing from the extract, linked through deposit D1)
  Bob    crm 200 + card C2 (tier 2: surname without the apostrophe + DOB + postal) + bureau B2 (tier 2, postal)
  Cara   crm 300 + card C3 (contact history account); crm 301 shares her national id hash but has another DOB:
         the conflict guard refuses the link. crm 301 + card C4 (agent note account).
  crm 400-403 share one national id hash (4 people): not evidence, no links.
  crm 500-505 six people at one postal code: not evidence for tier 2; card C5 matches crm 500 there: no link.
  card C8: Bob's surname, DOB and postal but another first initial: no link.
  card C9: Bob's surname and DOB, masked phone: no link.
  crm 600 + card C6: a Splink edge at 0.96.
"""
import datetime as dt

import duckdb
import pytest

from ontrack import config
from ontrack.l1_factory import contract_check, dq, gold, identity

D = dt.date


def _table(con, name, cols, rows):
    con.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {t}' for c, t in cols)})")
    if rows:
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})", rows)


CRM_COLS = [("crm_customer_id", "VARCHAR"), ("duplicate_of_crm_id", "VARCHAR"), ("national_id_hash", "VARCHAR"),
            ("surname_std", "VARCHAR"), ("given_std", "VARCHAR"), ("dob", "DATE"), ("postal6", "VARCHAR"),
            ("phone10", "VARCHAR"), ("last_profile_update_ts", "TIMESTAMP"), ("province_code", "VARCHAR"),
            ("time_zone", "VARCHAR"), ("preferred_language", "VARCHAR"),
            *[(c, "BOOLEAN") for c in ("consent_call", "consent_sms", "consent_email", "consent_push",
                                       "consent_autodialer", "internal_do_not_call_flag", "cease_communication_flag",
                                       "bankruptcy_flag", "consumer_proposal_flag", "deceased_flag",
                                       "third_party_authorised_flag", "power_of_attorney_flag",
                                       "legal_representative_flag", "credit_counselling_agency_flag",
                                       "vulnerability_flag")]]


def crm(cid, surname, given, dob, postal=None, phone=None, dup=None, nid=None, updated="2026-01-01", **flags):
    consent = {c: flags.get(c, True) for c in ("consent_call", "consent_sms", "consent_email", "consent_push",
                                                "consent_autodialer")}
    holds = {c: flags.get(c, False) for c in ("internal_do_not_call_flag", "cease_communication_flag",
                                               "bankruptcy_flag", "consumer_proposal_flag", "deceased_flag",
                                               "third_party_authorised_flag", "power_of_attorney_flag",
                                               "legal_representative_flag", "credit_counselling_agency_flag",
                                               "vulnerability_flag")}
    return (cid, dup, nid, surname, given, D.fromisoformat(dob) if dob else None, postal, phone,
            dt.datetime.fromisoformat(updated), "ON", "America/Toronto", "EN", *consent.values(), *holds.values())


PARTY_COLS = [("source_key", "VARCHAR"), ("surname_std", "VARCHAR"), ("given_std", "VARCHAR"), ("dob", "DATE"),
              ("postal6", "VARCHAR"), ("phone10", "VARCHAR")]


def build_book(con):
    for s in ("bronze", "silver", "gold"):
        con.execute(f"CREATE SCHEMA {s}")
    six = [crm(f"50{i}", f"PERSON{i}", "P", f"1960-01-0{i + 1}", postal="A0A0A0") for i in range(6)]
    _table(con, "silver.crm", CRM_COLS, [
        crm("100", "SMITH", "ALICE", "1980-01-05", postal="M5V2T6", phone="4165550001"),
        crm("101", "SMITH", "ALICE", "1980-01-05", dup="100", updated="2026-06-01", consent_sms=False,
            cease_communication_flag=True),
        crm("200", "O'BRIEN", "BOB", "1975-03-03", postal="K1A0B1", phone="6135550002"),
        crm("300", "CHEN", "CARA", "1990-01-01", nid="H3"),
        crm("301", "CHEN", "CARA", "1991-01-01", nid="H3"),
        *[crm(f"40{i}", f"NAME{i}", "N", f"1970-01-0{i + 1}", nid="H9") for i in range(4)],
        *six,
        crm("600", "PATEL", "RAJ", "1985-05-05"),
    ])
    _table(con, "silver.card_parties", PARTY_COLS, [
        ("C1", "SMITH", "A", D(1980, 1, 5), None, None),
        ("C2", "OBRIEN", "B", D(1975, 3, 3), "K1A0B1", None),
        ("C3", "CHEN", "C", D(1990, 1, 1), None, None),
        ("C4", "CHEN", "C", D(1991, 1, 1), None, None),
        ("C5", "PERSON0", "P", D(1960, 1, 1), "A0A0A0", None),
        ("C6", "PATEL", "R", D(1985, 5, 5), None, None),
        ("C8", "OBRIEN", "ZED", D(1975, 3, 3), "K1A0B1", None),
        ("C9", "OBRIEN", "B", D(1975, 3, 3), None, "613555xx02"),
    ])
    _table(con, "silver.loan_parties", PARTY_COLS, [("L1", "SMITH", "ALICE", D(1980, 1, 5), None, None)])
    _table(con, "silver.deposit_parties", PARTY_COLS, [("D1", "SMITH", None, None, None, None)])
    _table(con, "silver.bureau_parties", PARTY_COLS, [("B2", "O BRIEN", None, D(1975, 3, 3), "K1A0B1", None)])
    snap = D(2026, 9, 28)
    _table(con, "silver.card_accounts",
           [("card_account_id", "VARCHAR"), ("src_customer_ref", "VARCHAR"), ("current_balance", "DOUBLE"),
            ("credit_limit", "DOUBLE"), ("past_due_amount", "DOUBLE"), ("dpd", "INTEGER"), ("dpd_bucket", "VARCHAR"),
            ("account_status", "VARCHAR"), ("snapshot_date", "DATE")],
           [("C1-ACCT", "C1", 1200.0, 5000.0, 100.0, 45, "31-60", "open", snap),
            ("C2-ACCT", "C2", -50.0, 1000.0, 0.0, None, "1-30", "open", snap),     # credit balance; bucket, no dpd
            ("C3-ACCT", "C3", 300.0, 1000.0, 30.0, 10, "current", "open", snap),   # bucket contradicts dpd
            ("C4-ACCT", "C4", 0.0, 1000.0, 0.0, 0, "current", "open", snap),
            ("C5-ACCT", "C5", 0.0, 1000.0, 0.0, 0, "current", "open", snap),
            ("C6-ACCT", "C6", 0.0, 1000.0, 0.0, 0, "current", "open", snap)])
    _table(con, "silver.loan_accounts",
           [("loan_id", "VARCHAR"), ("src_customer_ref", "VARCHAR"), ("product_type", "VARCHAR"),
            ("total_outstanding", "DOUBLE"), ("past_due_amount", "DOUBLE"), ("dpd", "INTEGER"),
            ("dpd_bucket", "VARCHAR"), ("snapshot_date", "DATE"), ("pad_source_account", "VARCHAR")],
           [("L1-LOAN", "L1", "personal_loan", 8000.0, 400.0, 75, "61-90", snap, "D1-DEP"),
            ("L9-LOAN", "L9", None, 100.0, 0.0, 0, "current", snap, "EXTERNAL")])
    _table(con, "silver.deposit_accounts",
           [("deposit_account_id", "VARCHAR"), ("src_customer_ref", "VARCHAR"), ("product_type", "VARCHAR"),
            ("current_balance", "DOUBLE"), ("overdraft_limit", "DOUBLE"), ("overdraft_dpd", "INTEGER"),
            ("overdraft_dpd_bucket", "VARCHAR"), ("account_status", "VARCHAR"), ("snapshot_date", "DATE")],
           [("D1-DEP", "D1", "chequing", 2500.0, 500.0, 0, "current", "open", snap)])
    _table(con, "bronze.collections_cases",
           [("case_id", "VARCHAR"), ("coll_customer_ref", "VARCHAR"), ("account_ids", "VARCHAR"),
            ("current_dpd", "INTEGER"), ("current_bucket", "VARCHAR"), ("outcome", "VARCHAR")],
           [("CS-1", "100", '["C1-ACCT"]', 45, "31-60", None),
            ("CS-2", "100", "L1-LOAN; NOPE", 75, "31-60", None),           # stale source bucket
            ("CS-3", "200", "C2-ACCT", 0, "current", "cured"),
            ("CS-4", "999", "D1-DEP", 20, "1-30", None)])
    contact_cols = [("contact_id", "VARCHAR"), ("case_id", "VARCHAR"), ("crm_customer_id", "VARCHAR"),
                    ("account_id", "VARCHAR"), ("contact_ts_utc", "TIMESTAMP"), ("channel", "VARCHAR"),
                    ("channel_v2", "VARCHAR"), ("direction", "VARCHAR"), ("outcome_code", "VARCHAR"),
                    ("rpc_flag", "BOOLEAN"), ("payment_taken_flag", "BOOLEAN"), ("note_id", "VARCHAR"),
                    ("transcript_id", "VARCHAR")]
    ts = dt.datetime(2026, 9, 1, 10)
    _table(con, "bronze.contact_history", contact_cols, [
        ("k1", "CS-1X", "100", None, ts, "call", None, "outbound", "RPC", True, False, None, None),   # stray 'X'
        ("k2", "CS-77", "100", None, ts, None, "sms", "outbound", "NA", False, False, None, None),    # unknown case
        ("k3", "CS-3", "200", None, ts, "email", None, "outbound", "NA", False, False, None, None),
        ("k4", None, "300", "C3-ACCT", ts, "call", None, "inbound", "RPC", True, True, None, None),   # account link
    ])
    _table(con, "bronze.agent_notes", [("crm_customer_id", "VARCHAR"), ("account_id", "VARCHAR")],
           [("301", "C4-ACCT"), ("301", None)])
    _table(con, "silver.splink_edges", [("a", "VARCHAR"), ("b", "VARCHAR"), ("conf", "DOUBLE"), ("method", "VARCHAR")],
           [("crm:600", "card:C6", 0.96, "splink")])


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "l1.duckdb"
    con = duckdb.connect(str(path))
    build_book(con)
    con.close()
    opener = lambda read_only=False: duckdb.connect(str(path), read_only=read_only)  # noqa: E731
    for module in (identity, gold, contract_check, dq):
        monkeypatch.setattr(module, "connect", opener)
    return opener


def edges(con, sql):
    return {(a, b) for a, b, _ in con.execute(f"SELECT a, b, conf FROM ({sql})").fetchall()}


def test_tier1_edges(db):
    con = db()
    e = identity.EDGES_SQL
    assert edges(con, e["crm_duplicate"]) == {("crm:101", "crm:100")}
    assert edges(con, e["national_id"]) == {("crm:300", "crm:301")}          # H9 is shared by 4 people: no link
    assert edges(con, e["case_account"]) == {
        ("crm:100", "card:C1"),     # JSON list
        ("crm:100", "loan:L1"),     # ';' list with a space; the unknown id is ignored
        ("crm:200", "card:C2"),     # bare id
        ("crm:999", "cif:D1"),      # case whose CRM record is missing
        ("crm:300", "card:C3"),     # contact history account
        ("crm:301", "card:C4"),     # agent note account
    }
    assert edges(con, e["pad_link"]) == {("loan:L1", "cif:D1")}               # 'EXTERNAL' is not a bank account
    con.close()


def test_tier2_edges(db):
    con = db()
    got = set()
    for prefix, table in identity.PARTIES.items():
        for field, method in (("postal6", "name_dob_postal"), ("phone10", "name_dob_phone")):
            got |= edges(con, identity.tier2_sql(prefix, table, field, method))
    # Bob: card C2 and bureau B2 (surnames compared on letters only; bureau keys are 'cif:' nodes).
    # Not linked: C8 (other first initial), C9 (masked phone), C5 (postal shared by 6 people).
    assert got == {("crm:200", "card:C2"), ("crm:200", "cif:B2")}
    con.close()


@pytest.fixture()
def built(db):
    identity.main()
    gold.main()
    return db


def _xref(con):
    rows = con.execute("SELECT source_system, source_key, golden_id, match_method, match_confidence "
                       "FROM gold.customer_xref").fetchall()
    return {(s, k): (g, m, c) for s, k, g, m, c in rows}


def test_identity_main_clusters_people_and_logs_refusals(built):
    con = built(read_only=True)
    x = _xref(con)
    gid = lambda s, k: x[(s, k)][0]  # noqa: E731
    alice = {gid("crm", k) for k in ("100", "101", "999")} | {gid("cards", "C1"), gid("loans", "L1"),
                                                             gid("core_banking", "D1")}
    assert len(alice) == 1
    assert gid("cards", "C2") == gid("core_banking", "B2") == gid("crm", "200")
    assert gid("crm", "300") == gid("cards", "C3") != gid("crm", "301") == gid("cards", "C4")
    assert gid("crm", "600") == gid("cards", "C6")
    for s, k in [("cards", "C5"), ("cards", "C8"), ("cards", "C9"), ("crm", "400"), ("crm", "500")]:
        assert sum(v[0] == gid(s, k) for v in x.values()) == 1, (s, k)   # left on their own
    assert x[("crm", "101")][1:] == ("crm_duplicate", 0.99)
    assert x[("cards", "C2")][1:] == ("case_account", 0.98)        # strongest evidence wins over tier 2
    assert x[("core_banking", "B2")][1:] == ("name_dob_postal", 0.97)
    assert x[("cards", "C6")][1:] == ("splink", 0.96)
    assert x[("crm", "400")][1:] == ("singleton", 1.0)
    assert con.execute("SELECT a, b, method FROM silver.identity_refused").fetchall() == [
        ("crm:300", "crm:301", "national_id")]
    assert set(r[0] for r in con.execute("SELECT DISTINCT method FROM silver.identity_edges").fetchall()) == {
        "crm_duplicate", "national_id", "case_account", "pad_link", "name_dob_postal", "splink"}
    con.close()


def test_gold_customer_is_conservative_across_crm_records(built):
    con = built(read_only=True)
    alice = con.execute("""SELECT c.* FROM gold.c360_customer c JOIN gold.customer_xref x USING (golden_id)
                           WHERE x.source_system = 'crm' AND x.source_key = '100'""").fetchdf().iloc[0]
    assert alice.primary_crm_customer_id == "100"             # the original record, not the newer duplicate
    assert not alice.consent_sms and alice.consent_call       # consent only if every record allows it
    assert alice.cease_communication_flag                     # a hold on any record applies
    assert alice.crm_record_count == 2 and alice.source_key_count == 6
    assert alice.products_held == 3
    assert alice.total_exposure == 1200 + 8000                # the chequing deposit is not exposure
    assert alice.total_overdue == 500 and alice.max_dpd == 75
    assert (alice.open_case_count, alice.case_count) == (3, 3)
    assert alice.match_confidence_min == pytest.approx(0.98) and alice._dq_status == "ok"   # D1: case beats PAD
    bob = con.execute("""SELECT c.* FROM gold.c360_customer c JOIN gold.customer_xref x USING (golden_id)
                         WHERE x.source_system = 'crm' AND x.source_key = '200'""").fetchdf().iloc[0]
    assert bob.total_exposure == 0                            # a credit balance is floored at 0
    assert (bob.open_case_count, bob.case_count) == (0, 1)
    splink = con.execute("""SELECT _dq_status FROM gold.c360_customer c JOIN gold.customer_xref x USING (golden_id)
                            WHERE x.source_key = '600'""").fetchone()[0]
    assert splink == "ok"                                     # 0.96 >= 0.95
    no_crm = con.execute("""SELECT primary_crm_customer_id, consent_call FROM gold.c360_customer c
                            JOIN gold.customer_xref x USING (golden_id) WHERE x.source_key = 'C9'""").fetchone()
    assert no_crm == (None, None)                             # no CRM record: unknown, not 'consented'
    con.close()


def test_gold_buckets_and_contact_timeline(built):
    con = built(read_only=True)
    cases = dict(con.execute("SELECT case_id, (current_bucket_derived, bucket_conflict, golden_id IS NOT NULL) "
                             "FROM gold.case_360").fetchall())
    assert cases["CS-2"] == ("61-90", True, True)             # stale source bucket flagged
    assert cases["CS-1"] == ("31-60", False, True)
    assert cases["CS-4"][2]                                    # missing CRM record, still a golden_id
    acct = dict(con.execute("SELECT account_id, (dpd_bucket_derived, bucket_conflict) FROM gold.c360_account").fetchall())
    assert acct["C2-ACCT"] == (None, True)                    # a bucket but no dpd
    assert acct["C3-ACCT"] == ("1-30", True)                  # bucket contradicts dpd
    assert acct["C1-ACCT"] == ("31-60", False)
    t = dict(con.execute("SELECT contact_id, (case_id, case_id_raw, channel) FROM gold.contact_timeline").fetchall())
    assert t["k1"] == ("CS-1", "CS-1X", "call")               # stray 'X' stripped: a real case
    assert t["k2"] == (None, "CS-77", "sms")                  # unknown case: no case link; channel_v2 used
    assert t["k3"] == ("CS-3", "CS-3", "email")
    assert t["k4"][0] is None
    con.close()


def test_gold_refuses_a_protected_attribute(db):
    con = db()
    con.execute("ALTER TABLE bronze.collections_cases ADD COLUMN age INTEGER")   # would flow through case_360's c.*
    con.close()
    identity.main()
    with pytest.raises(RuntimeError, match="Protected attributes found in gold"):
        gold.main()


def test_contract_passes_on_a_clean_build_and_records_results(built, capsys):
    assert contract_check.main() is True
    con = built(read_only=True)
    res = con.execute("SELECT rule_id, passed FROM gold._contract_results ORDER BY rule_id").fetchall()
    assert res == [(f"Q{i}", True) for i in range(1, 9)]
    con.close()
    assert "all rules passed" in capsys.readouterr().out


def test_contract_fails_on_a_duplicate_golden_id_and_a_low_confidence_splink_link(built):
    con = built()
    con.execute("INSERT INTO gold.c360_customer SELECT * FROM gold.c360_customer LIMIT 1")
    con.execute("UPDATE gold.customer_xref SET match_confidence = 0.9 WHERE match_method = 'splink'")
    con.close()
    assert contract_check.main() is False
    con = built(read_only=True)
    failed = [r[0] for r in con.execute("SELECT rule_id FROM gold._contract_results WHERE NOT passed ORDER BY 1").fetchall()]
    assert failed == ["Q1", "Q2"]
    con.close()


def test_dq_report_is_generated_from_the_pipeline_tables(built, tmp_path, monkeypatch):
    contract_check.main()
    con = built()
    con.execute("CREATE TABLE bronze._load_log AS SELECT 'customers' AS table_name, 'csv' AS kind, 10 AS rows, "
                "12 AS expected_rows, ['extra_col'] AS extra_cols, []::VARCHAR[] AS missing_cols")
    con.execute("CREATE TABLE bronze._cast_failures (table_name VARCHAR, column_name VARCHAR, target_type VARCHAR, "
                "failed_count BIGINT, sample_value VARCHAR)")
    con.execute("CREATE TABLE silver._dq_issues AS SELECT 'Province spelled out' AS issue, 'customers' AS table_name, "
                "10657::BIGINT AS records_affected, 'Standardised' AS handling")
    con.execute("CREATE TABLE bronze.ops_events AS SELECT 'E1' AS event_id, 'dialer_outage' AS event_type, "
                "TIMESTAMP '2026-09-01 10:00' AS start_ts, TIMESTAMP '2026-09-01 12:00' AS end_ts, "
                "'contact_history' AS affected_tables, 'Dialer down' AS description")
    con.execute("CREATE TABLE gold.match_review_queue AS SELECT 'pending' AS steward_status")
    con.execute("CREATE TABLE silver.splink_validation AS SELECT 5000 AS holdout_keys, 4970 AS auto_linked, "
                "0.998 AS precision, 0.994 AS recall")
    con.close()
    out = tmp_path / "data_quality_report.md"
    monkeypatch.setattr(config, "deliverable_path", lambda rel: out)
    dq.main()
    text = out.read_text(encoding="utf-8")
    assert "| customers | csv | 10 | 12 | MISMATCH | extra_col |  |" in text      # count check and schema drift
    assert "None found." in text                                                # no cast failures
    assert "| Province spelled out | customers | 10,657 | Standardised |" in text
    assert "| E1 | dialer_outage |" in text and "labelled outage-affected" in text
    assert "| Links refused by the conflict guard (would merge people with different dates of birth) | 1 |" in text
    assert "| Q1 | golden_id unique and not null | 0.0 | 0.0 | pass |" in text
    assert "**1**" in text                                                      # grey-zone queue size
    # Alice's records 100 and 101 share a DOB; Cara's two DOBs were never merged
    assert "| Golden ids holding records with different dates of birth (possible wrong merges) | 0 |" in text


def test_md_table_formats_numbers_and_blanks():
    assert dq.md_table(["a", "b", "c"], [(1234567, None, "x")]) == "| a | b | c |\n|---|---|---|\n| 1,234,567 |  | x |"


def test_identity_without_splink_or_conflicts(db):
    con = db()
    con.execute("DROP TABLE silver.splink_edges")
    con.execute("UPDATE silver.crm SET national_id_hash = NULL WHERE crm_customer_id = '301'")
    con.close()
    identity.main()
    con = db(read_only=True)
    assert con.execute("SELECT count(*) FROM silver.identity_refused").fetchone()[0] == 0
    assert con.execute("SELECT match_method FROM gold.customer_xref WHERE source_key = 'C6'").fetchone()[0] == "singleton"
    con.close()


def test_golden_id_collision_is_refused(monkeypatch):
    import hashlib

    class Same:
        def hexdigest(self):
            return "0" * 40
    monkeypatch.setattr(hashlib, "sha1", lambda b: Same())
    uf = identity.UnionFind()
    uf.parent.update({"crm:1": "crm:1", "crm:2": "crm:2"})
    with pytest.raises(RuntimeError, match="collision"):
        identity.golden_ids(uf)


def test_union_of_keys_already_together_changes_nothing():
    uf = identity.UnionFind()
    uf.union("crm:2", "card:9")
    before = dict(uf.parent)
    uf.union("card:9", "crm:2")
    assert uf.parent == before


def test_build_runs_the_steps_in_order_with_a_fresh_first_identity_pass(db, monkeypatch):
    from ontrack.l1_factory import build, probabilistic, silver
    calls = []
    for m in (silver, identity, probabilistic, gold, contract_check, dq):
        monkeypatch.setattr(m, "main", lambda m=m: calls.append(m.__name__.rsplit(".", 1)[-1]))
    monkeypatch.setattr(build, "connect", db)
    build.main()
    assert calls == ["silver", "identity", "probabilistic", "identity", "gold", "contract_check", "dq"]
    con = db(read_only=True)
    assert con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'splink_edges'").fetchone()[0] == 0
    con.close()


def test_silver_dq_only_recounts_issues_without_rebuilding(db, monkeypatch):
    from ontrack.l1_factory import silver
    monkeypatch.setattr(silver, "connect", db)
    monkeypatch.setattr(silver, "STEPS", {"crm": "SELECT 1 AS wiped"})
    monkeypatch.setattr(silver, "DQ_CHECKS", [("Cases in the book", "collections_cases",
                                                "SELECT count(*) FROM bronze.collections_cases", "Counted")])
    silver.main(dq_only=True)
    con = db(read_only=True)
    assert con.execute("SELECT count(*) FROM silver.crm").fetchone()[0] > 1          # not rebuilt
    assert con.execute("SELECT records_affected FROM silver._dq_issues").fetchall() == [(4,)]
    con.close()
    silver.main()
    con = db(read_only=True)
    assert con.execute("SELECT * FROM silver.crm").fetchall() == [(1,)]             # rebuilt from STEPS
    con.close()


def test_contract_threshold_is_inclusive_and_empty_counts_as_zero(built, tmp_path, monkeypatch):
    rules = tmp_path / "contract.yaml"
    rules.write_text("""id: TEST
version: 1
quality:
  - {id: R1, name: at the threshold, sql: "SELECT 1.0", threshold: 1.0, on_failure: none}
  - {id: R2, name: no rows, sql: "SELECT NULL", threshold: 0, on_failure: none}
  - {id: R3, name: over, sql: "SELECT 2", threshold: 1, on_failure: none}
""", encoding="utf-8")
    monkeypatch.setattr(contract_check, "CONTRACT", rules)
    assert contract_check.main() is False
    con = built(read_only=True)
    assert con.execute("SELECT rule_id, observed, passed FROM gold._contract_results ORDER BY 1").fetchall() == [
        ("R1", 1.0, True), ("R2", 0.0, True), ("R3", 2.0, False)]
    con.close()
