"""Layer 3 structured features: every window, tie-break and fallback in features.py, on a synthetic database (owner: P3).

as_of = 2026-03-01. A contact's ``ago`` is whole days before as_of minus one (a contact on 28 Feb is ago 0), so
"in the last 7 days" means ago 0-6. Account month-ends count only when at least 60 days old (on or before 31 Dec)
and at most 270 days old; salary months are the 9 before March, "recent" being Dec-Feb.
"""
import datetime as dt

import duckdb
import pandas as pd
import pytest

from ontrack.l3_features.structured import features as F

AS_OF = "2026-03-01"
MILESTONES = (7, 14, 21, 30, 45, 60, 90)


def _case(case_id, golden_id, opened, entry, outcome=None, outcome_date=None, product="card",
          reason="missed_payment", **milestones):
    row = {"case_id": case_id, "golden_id": golden_id, "crm_customer_id": "C" + golden_id[1:],
           "case_open_date": dt.date.fromisoformat(opened), "outcome": outcome,
           "outcome_date": dt.date.fromisoformat(outcome_date) if outcome_date else None, "cure_date": None,
           "entry_overdue": entry, "prior_cases_12m": 2, "primary_product": product, "case_open_reason": reason}
    row.update({f"overdue_at_day_{d}": milestones.get(f"d{d}") for d in MILESTONES})
    return row


def _contact(cid, case_id, ts, rpc=False, hour=12, direction="outbound", amount=None, **flags):
    return {"contact_id": cid, "case_id": case_id, "contact_ts_utc": pd.Timestamp(ts), "rpc_flag": rpc,
            "direction": direction, "payment_amount": amount, "contact_hour_local": hour,
            **{f: flags.get(f, False) for f in (
                "payment_taken_flag", "link_payment_flag", "app_payment_after_contact_flag",
                "ivr_self_serve_payment_flag", "link_clicked_flag", "email_clicked_flag", "callback_requested_flag",
                "hardship_mentioned_flag", "dispute_raised_flag")}}


CASES = pd.DataFrame([
    # T1: 35 days old -> overdue at the day-30 milestone; the day-45 value is still in the future
    _case("T1", "G1", "2026-01-25", 100.0, product="loc", reason="overlimit",
          d7=110.0, d14=120.0, d21=130.0, d30=150.0, d45=999.0),
    # T2: 3 days old, nothing overdue at entry, unknown product and reason
    _case("T2", "G1", "2026-02-26", 0.0, product="boat_loan", reason=None, d7=50.0),
    # T3: same person, closed before as_of -> neither in the population nor another open case
    _case("T3", "G1", "2025-12-01", 80.0, outcome="paid", outcome_date="2026-02-15"),
    # T4: same person, opened after as_of -> neither
    _case("T4", "G1", "2026-04-01", 80.0),
    # T5: 120 days old, day-90 value missing -> falls back to day 60
    _case("T5", "G2", "2025-11-01", 200.0, d30=210.0, d60=300.0),
    # T6: same person as T5, closed *after* as_of -> still open at as_of
    _case("T6", "G2", "2026-02-01", 50.0, outcome="charged_off", outcome_date="2026-03-20"),
    # T7: 26 days old -> day 21; the day-30 value is still 4 days away. A person with no other data.
    _case("T7", "G3", "2026-02-03", 100.0, d7=110.0, d14=120.0, d21=130.0, d30=999.0),
])

CONTACTS = pd.DataFrame([
    _contact("c1", "T1", "2026-02-28 23:59", rpc=True, hour=18, direction="inbound", link_clicked_flag=True),  # ago 0
    _contact("c2", "T1", "2026-02-22 10:00", rpc=True, hour=10),                                  # ago 6: in 7 days
    _contact("c3", "T1", "2026-02-21 10:00", amount=40.0, payment_taken_flag=True),               # ago 7: not 7 days
    _contact("c4", "T1", "2026-01-30 09:00", amount=25.0, ivr_self_serve_payment_flag=True,
             callback_requested_flag=True),                                                       # ago 29: in 30 days
    _contact("c5", "T1", "2026-01-29 09:00", amount=1000.0, app_payment_after_contact_flag=True,
             hardship_mentioned_flag=True, callback_requested_flag=True),                         # ago 30: not 30 days
    _contact("c6", "T1", "2025-11-15 09:00", amount=500.0, payment_taken_flag=True,
             dispute_raised_flag=True),                                                           # ago 105: not 90 days
    _contact("c7", "T1", "2026-03-01 00:00", rpc=True, amount=9999.0, payment_taken_flag=True),   # at as_of: a label
    _contact("c8", "T5", "2026-02-20 08:00", rpc=True, hour=None),                                # rpc, hour unknown
])


@pytest.fixture()
def con():
    c = duckdb.connect()
    for s in ("gold", "bronze"):
        c.execute(f"CREATE SCHEMA {s}")
    c.register("cases_df", CASES)
    milestones = ", ".join(f"overdue_at_day_{d}::DOUBLE AS overdue_at_day_{d}" for d in MILESTONES)
    c.execute(f"""CREATE TABLE gold.case_360 AS SELECT * EXCLUDE (outcome_date, cure_date, {", ".join(
        f"overdue_at_day_{d}" for d in MILESTONES)}), outcome_date::DATE AS outcome_date, cure_date::DATE AS cure_date,
        {milestones} FROM cases_df""")
    c.register("contacts_df", CONTACTS)
    c.execute("CREATE TABLE gold.contact_timeline AS SELECT contact_id, case_id, contact_ts_utc, rpc_flag FROM contacts_df")
    c.execute("CREATE TABLE bronze.contact_history AS SELECT * EXCLUDE (case_id, contact_ts_utc, rpc_flag, payment_amount, "
              "contact_hour_local), payment_amount::DOUBLE AS payment_amount, "
              "contact_hour_local::INT AS contact_hour_local FROM contacts_df")
    c.execute("""CREATE TABLE gold.customer_xref AS SELECT * FROM (VALUES
        ('G1', 'core_banking', 'B1'), ('G2', 'core_banking', 'B2'),
        ('G1', 'crm', 'C1'), ('G2', 'crm', 'C2')) t(golden_id, source_system, source_key)""")
    c.execute("""CREATE TABLE bronze.bureau_history AS SELECT * FROM (VALUES
        ('B1', DATE '2026-01-01', 800, 0.1, 0, 0),      -- older pull
        ('B1', DATE '2026-02-10', 650, 0.4, 1, 2),      -- same day as the external pull below
        ('B2', DATE '2026-02-20', NULL, 0.9, 9, 9),     -- no score: ignored
        ('B2', DATE '2026-01-31', 700, 0.2, 0, 1)
    ) t(bank_subject_ref, pull_date, risk_score, revolving_utilisation, delinquent_trades_count, inquiries_hard_6m)""")
    c.execute("""CREATE TABLE bronze.external AS SELECT * FROM (VALUES
        ('B1', DATE '2026-02-10', 600, 0.6, 3, 1)
    ) t(bank_subject_ref, pull_date, risk_score, revolving_utilisation, off_us_delinquent_trades, inquiries_hard_6m)""")
    c.execute("""CREATE TABLE bronze.salary_credit_history AS SELECT * FROM (VALUES
        ('C1', '2025-05', false, 99999.0, 'Y'),         -- 10 months before March: outside the 9-month window
        ('C1', '2025-06', false, 3000.0, 'N'), ('C1', '2025-07', false, 3000.0, 'Y'),
        ('C1', '2025-08', false, 3000.0, 'Y'), ('C1', '2025-09', false, 3000.0, 'Y'),
        ('C1', '2025-10', false, 3000.0, 'Y'), ('C1', '2025-11', true, 3000.0, 'Y'),
        ('C1', '2025-12', false, 3000.0, 'Y'),
        ('C1', '2026-01', true, 1500.0, 'Y'),
        ('C1', '2026-02', true, 1500.0, 'Y'), ('C1', '2026-02', false, 500.0, 'N'),   -- two credits, one month
        ('C1', '2026-03', true, 0.0, 'Y'),              -- as_of's own month: not used
        ('C2', '2026-01', false, 0.0, 'N')
    ) t(crm_customer_id, credit_month, gap_flag, credit_amount_total, employer_flag)""")
    c.execute("""CREATE TABLE bronze.account_monthly_snapshot AS SELECT * FROM (VALUES
        ('C1', '2026-01-31', 9999.0, 1.0, 1.0, 0.0, 120, true),   -- under 60 days old: not used
        ('C1', '2025-12-31', 1100.0, 1000.0, 50.0, 50.0, 30, true),
        ('C1', '20251231', 400.0, 1000.0, 20.0, 0.0, 60, false),  -- second account, same month, YYYYMMDD
        ('C1', '11/30/2025', 0.0, 1000.0, 50.0, 60.0, 0, false),  -- MM/DD/YYYY
        ('C1', '31/10/2025', 0.0, 1000.0, 0.0, 0.0, 0, false),    -- DD/MM/YYYY; nothing due counts as paid
        ('C1', '2025-09-30', 0.0, 1000.0, 10.0, 10.0, 0, false),
        ('C1', '2025-08-31', 0.0, 1000.0, 10.0, 10.0, 0, false),
        ('C1', '2025-07-31', 0.0, 1000.0, 10.0, 10.0, 0, false),
        ('C1', '2025-06-30', 0.0, 1000.0, 10.0, 0.0, 0, false),   -- 7th month back: outside the 6
        ('C1', '2025-05-31', 0.0, 1000.0, 10.0, 0.0, 90, true),   -- over 270 days old: not used
        ('C2', '2025-12-31', 300.0, 0.0, 0.0, 0.0, NULL, NULL),   -- no limit: utilisation unknown
        ('C2', '2025-05-31', 0.0, 100.0, 0.0, 0.0, 0, false)      -- 274 days old: outside 270 days, even with a gap
    ) t(crm_customer_id, month_end_date, balance, limit_or_original_amount, minimum_due, payment_made, dpd,
        overlimit_flag)""")
    yield c
    c.close()


@pytest.fixture()
def f(con):
    F.build_case_features(con, AS_OF)
    return con.execute(f"SELECT * FROM {F.TABLE} ORDER BY case_id").fetchdf().set_index("case_id")


def test_population_and_other_open_cases(f):
    assert list(f.index) == ["T1", "T2", "T5", "T6", "T7"]    # T3 closed before as_of, T4 opened after
    assert f.loc["T1", "other_open_cases"] == 1 and f.loc["T2", "other_open_cases"] == 1
    assert f.loc["T5", "other_open_cases"] == 1               # T6 closes only after as_of
    assert f.loc["T7", "other_open_cases"] == 0


def test_case_trajectory_uses_only_reached_milestones(f):
    assert f.loc["T1", "case_age_days"] == 35
    assert f.loc["T1", "overdue_now"] == 150                  # day 30, not the future day-45 value
    assert f.loc["T1", "overdue_growth_pct"] == pytest.approx(0.5)
    assert f.loc["T5", "overdue_now"] == 300                  # day 90 missing -> day 60
    assert f.loc["T7", "overdue_now"] == 130                  # day 21; day 30 not reached
    assert f.loc["T2", "overdue_now"] == 0                    # 3 days old: entry value
    assert f.loc["T2", "overdue_growth_pct"] == 0             # nothing overdue at entry: no division


def test_product_and_reason_codes(f):
    assert (f.loc["T1", "product_code"], f.loc["T1", "open_reason_code"]) == (5, 3)
    assert (f.loc["T2", "product_code"], f.loc["T2", "open_reason_code"]) == (0, 0)   # unknown / missing -> 0
    assert f.loc["T1", "prior_cases_12m"] == 2


def test_contact_windows_and_their_boundaries(f):
    t1 = f.loc["T1"]
    assert t1.contacts_total == 6                             # the as_of-midnight contact is a label, not a feature
    assert (t1.contacts_7d, t1.contacts_30d) == (2, 4)        # ago 6 is in, ago 7 out; ago 29 in, ago 30 out
    assert (t1.inbound_30d, t1.rpc_30d, t1.rpc_rate_30d) == (1, 2, 0.5)
    assert (t1.days_since_last_contact, t1.days_since_last_rpc) == (0, 0)
    assert (t1.payments_total, t1.payments_30d, t1.days_since_last_payment) == (4, 2, 7)
    assert t1.payment_amount_90d == 40 + 25 + 1000            # the 105-day-old payment is outside 90 days
    assert (t1.link_clicks_30d, t1.callback_requested_30d) == (1, 1)
    assert (t1.hardship_mentioned_any, t1.dispute_raised_any) == (1, 1)   # "any": no window


def test_no_contacts_gives_neutral_values_not_nulls(f):
    t2 = f.loc["T2"]
    assert (t2.contacts_total, t2.contacts_30d, t2.rpc_rate_30d, t2.payment_amount_90d) == (0, 0, 0, 0)
    assert (t2.days_since_last_contact, t2.days_since_last_rpc, t2.days_since_last_payment) == (999, 999, 999)
    assert pd.isna(t2.best_rpc_hour)


def test_a_person_with_no_bureau_salary_or_account_data(f):
    t7 = f.loc["T7"]
    assert t7[["bureau_score", "bureau_age_days", "salary_drop_pct", "acct_utilisation", "acct_max_dpd",
               "acct_months_min_paid_6m"]].isna().all()       # unknown stays unknown (the model handles missing)
    assert (t7.salary_gap_months_3m, t7.has_payroll) == (0, 0)


def test_best_rpc_hour_ties_go_to_the_earlier_hour(f):
    assert f.loc["T1", "best_rpc_hour"] == 10                 # one right-party contact at 18:00, one at 10:00
    assert pd.isna(f.loc["T5", "best_rpc_hour"])               # its only right-party contact has no hour


def test_bureau_latest_pull_and_same_day_tie_break(f):
    t1 = f.loc["T1"]
    assert (t1.bureau_score, t1.bureau_utilisation, t1.bureau_delinquent_trades) == (600, 0.6, 3)
    assert (t1.bureau_inquiries_6m, t1.bureau_age_days) == (1, 19)
    assert (f.loc["T5", "bureau_score"], f.loc["T5", "bureau_age_days"]) == (700, 29)   # unscored pull skipped


def test_salary_recent_vs_prior_months(f):
    t1 = f.loc["T1"]
    assert t1.salary_gap_months_3m == 2                       # Jan and Feb; Nov is too early, March is as_of's month
    assert t1.salary_drop_pct == pytest.approx((6500 / 3 - 3000) / 3000)   # Feb's two credits are summed
    assert t1.has_payroll == 1                                # any month with a payroll credit
    t5 = f.loc["T5"]
    assert pd.isna(t5.salary_drop_pct)                        # no earlier months to compare with
    assert (t5.salary_gap_months_3m, t5.has_payroll) == (0, 0)


def test_account_months_formats_lag_and_six_month_window(f):
    t1 = f.loc["T1"]
    assert t1.acct_utilisation == pytest.approx(1500 / 2000)  # both December accounts, summed
    assert (t1.acct_max_dpd, t1.acct_overlimit) == (60, 1)    # January is inside the 60-day lag
    assert t1.acct_months_min_paid_6m == 5                    # Nov, Oct (DD/MM), Sep, Aug, Jul; Dec missed one
    t5 = f.loc["T5"]
    assert pd.isna(t5.acct_utilisation)                       # no limit: no ratio
    assert (t5.acct_max_dpd, t5.acct_overlimit, t5.acct_months_min_paid_6m) == (0, 0, 1)   # May is too old


def test_an_older_table_layout_is_replaced(con):
    con.execute("CREATE SCHEMA features")
    con.execute(f"CREATE TABLE {F.TABLE} AS SELECT 'old' AS case_id, DATE '{AS_OF}' AS as_of_date")
    assert F.build_case_features(con, AS_OF) == 5
    cols = [r[0] for r in con.execute(f"DESCRIBE {F.TABLE}").fetchall()]
    assert set(F.FEATURE_COLUMNS) <= set(cols)


def test_helper_tables_are_temporary_and_built_once(con):
    F.build_case_features(con, AS_OF)
    F.build_case_features(con, "2026-02-01")
    temp = con.execute("SELECT table_name FROM duckdb_tables() WHERE temporary ORDER BY 1").fetchall()
    assert [t[0] for t in temp] == sorted(F._PREPARE)
    assert con.execute("SELECT count(*) FROM duckdb_tables() WHERE schema_name IN ('gold', 'bronze') "
                       "AND table_name LIKE '_p3%'").fetchone()[0] == 0


@pytest.mark.parametrize("bad", ["2026-02-30", "not a date", "2026-13-01"])
def test_invalid_as_of_dates_are_refused_before_any_sql(bad):
    with pytest.raises(ValueError):
        F.feature_sql(bad)


def test_as_of_accepts_dates_and_timestamps():
    assert F.feature_sql(dt.date(2026, 3, 1)) == F.feature_sql("2026-03-01 12:30:00") == F.feature_sql(AS_OF)
