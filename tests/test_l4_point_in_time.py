"""Point-in-time tests for features and labels (issue #3), on a tiny synthetic database (owner: P3)."""
import duckdb
import pandas as pd
import pytest

from ontrack.l3_features.structured.features import FEATURE_COLUMNS, build_case_features
from ontrack.l4_nba.models import load_frame

AS_OF = "2026-02-01"


@pytest.fixture()
def con():
    c = duckdb.connect()
    for s in ("gold", "bronze", "features"):
        c.execute(f"CREATE SCHEMA {s}")
    milestones = ", ".join(f"NULL::DOUBLE AS overdue_at_day_{d}" for d in (7, 14, 21, 30, 45, 60, 90))
    c.execute(f"""CREATE TABLE gold.case_360 AS SELECT * FROM (VALUES
        -- A: open at as_of, cured 19 days later           -> in population, self_cure = 1
        ('A', 'G1', 'C1', DATE '2026-01-10', 'cured', DATE '2026-02-20', DATE '2026-02-20'),
        -- B: open at as_of, cured 73 days later           -> in population, self_cure = 0
        ('B', 'G2', 'C2', DATE '2026-01-15', 'cured', DATE '2026-04-15', DATE '2026-04-15'),
        -- C: opened after as_of                          -> not in population
        ('C', 'G3', 'C3', DATE '2026-02-15', NULL, NULL, NULL),
        -- D: cured before as_of                          -> not in population
        ('D', 'G4', 'C4', DATE '2025-12-01', 'cured', DATE '2026-01-20', DATE '2026-01-20'),
        -- E: still open today                            -> in population, self_cure = 0
        ('E', 'G5', 'C5', DATE '2026-01-20', NULL, NULL, NULL)
    ) t(case_id, golden_id, crm_customer_id, case_open_date, outcome, outcome_date, cure_date),
    LATERAL (SELECT 100.0 AS entry_overdue, 0 AS prior_cases_12m, 'card' AS primary_product,
                    'missed_payment' AS case_open_reason, {milestones})""")
    c.execute("""CREATE TABLE gold.contact_timeline AS SELECT * FROM (VALUES
        ('k1', 'B', TIMESTAMP '2026-01-31 10:00:00', true),   -- before as_of: a feature, not a label
        ('k2', 'B', TIMESTAMP '2026-02-01 00:00:00', false),  -- at as_of 00:00: a label, not a feature
        ('k3', 'E', TIMESTAMP '2026-02-08 00:00:00', false)   -- 7 days after: outside the label window
    ) t(contact_id, case_id, contact_ts_utc, rpc_flag)""")
    c.execute("""CREATE TABLE bronze.contact_history AS SELECT contact_id, 'outbound' AS direction,
        true AS payment_taken_flag, false AS link_payment_flag, false AS app_payment_after_contact_flag,
        false AS ivr_self_serve_payment_flag, 50.0 AS payment_amount, false AS link_clicked_flag,
        false AS email_clicked_flag, false AS callback_requested_flag, false AS hardship_mentioned_flag,
        false AS dispute_raised_flag, 12 AS contact_hour_local FROM gold.contact_timeline""")
    c.execute("""CREATE TABLE gold.customer_xref AS SELECT * FROM (VALUES
        ('G1', 'core_banking', 'B1'), ('G2', 'core_banking', 'B2'), ('G5', 'core_banking', 'B5'),
        ('G1', 'crm', 'C1'), ('G2', 'crm', 'C2'), ('G5', 'crm', 'C5')) t(golden_id, source_system, source_key)""")
    c.execute("""CREATE TABLE bronze.bureau_history AS SELECT * FROM (VALUES
        ('B1', DATE '2025-10-15', 700, 0.3, 0, 1),
        ('B1', DATE '2026-04-15', 400, 0.9, 5, 9)     -- after as_of: must not be used
    ) t(bank_subject_ref, pull_date, risk_score, revolving_utilisation, delinquent_trades_count, inquiries_hard_6m)""")
    c.execute("""CREATE TABLE bronze.external AS SELECT * FROM (VALUES
        ('B2', DATE '2026-03-01', 500, 0.5, 2, 4)     -- after as_of: must not be used
    ) t(bank_subject_ref, pull_date, risk_score, revolving_utilisation, off_us_delinquent_trades, inquiries_hard_6m)""")
    c.execute("""CREATE TABLE bronze.salary_credit_history AS SELECT * FROM (VALUES
        ('C1', '2026-01', true, 0.0, 'Y'), ('C1', '2026-02', true, 0.0, 'Y')   -- Feb is not before as_of
    ) t(crm_customer_id, credit_month, gap_flag, credit_amount_total, employer_flag)""")
    c.execute("""CREATE TABLE bronze.account_monthly_snapshot AS SELECT * FROM (VALUES
        ('C1', '2025-11-30', 500.0, 1000.0, 50.0, 50.0, 0, false),
        ('C1', '01/31/2026', 900.0, 1000.0, 50.0, 0.0, 30, true)    -- under 60 days before as_of
    ) t(crm_customer_id, month_end_date, balance, limit_or_original_amount, minimum_due, payment_made, dpd,
        overlimit_flag)""")
    yield c
    c.close()


def frame(con):
    build_case_features(con, AS_OF)
    return con.execute("SELECT * FROM features.case_features ORDER BY case_id").fetchdf().set_index("case_id")


def test_population_is_open_and_unresolved_at_as_of(con):
    assert list(frame(con).index) == ["A", "B", "E"]


def test_features_use_only_the_past(con):
    f = frame(con)
    assert f.loc["B", "contacts_total"] == 1          # the as_of-midnight contact is not a feature
    assert f.loc["B", "payments_total"] == 1
    assert f.loc["A", "bureau_score"] == 700          # the April pull is not used
    assert pd.isna(f.loc["B", "bureau_score"])         # the only pull is after as_of
    assert f.loc["A", "salary_gap_months_3m"] == 1    # January only
    assert f.loc["A", "acct_max_dpd"] == 0            # the January month-end is inside the 60-day lag
    assert set(FEATURE_COLUMNS) <= set(f.columns)


def test_labels_are_strictly_after_as_of(con):
    build_case_features(con, AS_OF)
    cure = load_frame(con, "self_cure_30d", [AS_OF]).set_index("case_id")["label"].to_dict()
    pay = load_frame(con, "payment_7d", [AS_OF]).set_index("case_id")["label"].to_dict()
    assert cure == {"A": 1, "B": 0, "E": 0}
    assert pay == {"A": 0, "B": 1, "E": 0}          # E's payment is 7 days later: outside [as_of, as_of+7d)


def test_rebuilding_a_date_keeps_other_dates(con):
    build_case_features(con, AS_OF)
    build_case_features(con, "2026-01-25")
    build_case_features(con, AS_OF)
    dates = con.execute("SELECT as_of_date::VARCHAR, count(*) FROM features.case_features GROUP BY 1 ORDER BY 1").fetchall()
    assert dates == [("2026-01-25", 3), ("2026-02-01", 3)]


@pytest.mark.parametrize("extra", ["0 AS gender_code", "0 AS age", "true AS cure_flag", "DATE '2026-03-01' AS outcome_date"])
def test_protected_or_outcome_columns_are_refused(con, monkeypatch, extra):
    # Governance guard: if a feature SQL ever selects a protected attribute or an outcome, nothing is written
    import ontrack.l3_features.structured.features as F
    original = F.feature_sql
    monkeypatch.setattr(F, "feature_sql", lambda d: f"SELECT *, {extra} FROM ({original(d)})")
    with pytest.raises(RuntimeError, match="Outcome or protected"):
        F.build_case_features(con, AS_OF)
    assert con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = 'case_features'").fetchone()[0] == 0


def test_unexpected_feature_columns_are_refused(con, monkeypatch):
    import ontrack.l3_features.structured.features as F
    original = F.feature_sql
    monkeypatch.setattr(F, "feature_sql", lambda d: f"SELECT *, 1 AS surprise_column FROM ({original(d)})")
    with pytest.raises(RuntimeError, match="differ from FEATURE_COLUMNS"):
        F.build_case_features(con, AS_OF)
