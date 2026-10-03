"""Structured case features for Layer 4 (owner: P3).

One function, ``build_case_features(con, as_of_date)``, builds the features for training (past dates) and
for live scoring (the snapshot date) with the same code.

Point-in-time rules (issue #3):
  * population = cases **open and unresolved at as_of**: opened on or before as_of, not cured and not
    closed by then. At the snapshot date this is exactly the open book (96,000 cases).
  * every input is restricted to what was known at as_of: contacts with ``contact_ts_utc <= as_of``,
    case trajectory milestones up to the case's age, bureau pulls with ``pull_date <= as_of``, salary
    months before as_of's month, account month-ends at least 60 days before as_of (the snapshot table
    lags; the same lag is used for training and scoring, so both see the same kind of data).
  * nothing is read from snapshot-time aggregates (``gold.c360_*`` totals, ``current_dpd``,
    ``treatment_path``, ``payments_since_open_*``, ``accounts_in_case_count``, ...): those describe 28 Sep
    and would leak the future into a training row dated months earlier (e.g. only cases still open on
    28 Sep have more than one account in the case, so that column alone gives away "never cured").
  * outcome columns and ``config.PROTECTED_COLUMNS`` are never read; ``promises_to_pay`` is not used.

``features.case_features`` holds one row per (case_id, as_of_date); building a date replaces only that
date's rows, so monthly training dates stack in the same table.
"""
from __future__ import annotations

import datetime as dt

from ontrack import config

TABLE = "features.case_features"
KEYS = ["case_id", "golden_id", "crm_customer_id", "as_of_date"]
# Informational columns kept in the table but never fed to a model.
INFO_COLUMNS = ["best_rpc_hour"]

FEATURE_COLUMNS = [
    # case, known at open
    "entry_overdue", "prior_cases_12m", "product_code", "open_reason_code",
    # case trajectory up to as_of
    "case_age_days", "overdue_now", "overdue_growth_pct", "other_open_cases",
    # contact history up to as_of
    "contacts_total", "contacts_7d", "contacts_30d", "inbound_30d", "rpc_30d", "rpc_rate_30d",
    "days_since_last_contact", "days_since_last_rpc", "payments_total", "payments_30d",
    "payment_amount_90d", "days_since_last_payment", "link_clicks_30d", "callback_requested_30d",
    "hardship_mentioned_any", "dispute_raised_any",
    # bureau, latest pull on or before as_of
    "bureau_score", "bureau_utilisation", "bureau_delinquent_trades", "bureau_inquiries_6m", "bureau_age_days",
    # income, salary months before as_of
    "salary_gap_months_3m", "salary_drop_pct", "has_payroll",
    # accounts, month-ends >= 60 days before as_of
    "acct_months_min_paid_6m", "acct_utilisation", "acct_max_dpd", "acct_overlimit",
]

OUTCOME_COLUMNS = frozenset({
    "cure_flag", "cure_date", "days_to_cure", "outcome", "outcome_date", "case_status", "case_status_date",
    "current_dpd", "current_bucket", "treatment_path", "payments_since_open_amount", "payments_since_open_count",
    "dpd_at_day_7", "dpd_at_day_14", "dpd_at_day_21", "dpd_at_day_30", "dpd_at_day_45", "dpd_at_day_60",
    "dpd_at_day_90", "accounts_in_case_count", "roll_forward_count", "roll_back_count", "chargeoff_flag", "nba_recommendation_last",
})

PRODUCT_CODES = {"card": 1, "personal_loan": 2, "overdraft": 3, "auto_loan": 4, "loc": 5, "mortgage": 6}
OPEN_REASON_CODES = {"missed_payment": 1, "returned_pad": 2, "overlimit": 3, "manual": 4}

# Helper tables, built once per connection as TEMP tables (nothing is written to the shared schemas).
_PREPARE = {
    "_p3_contacts": """
        SELECT t.case_id, t.contact_ts_utc, t.rpc_flag, h.direction,
               (coalesce(h.payment_taken_flag, false) OR coalesce(h.link_payment_flag, false)
                OR coalesce(h.app_payment_after_contact_flag, false)
                OR coalesce(h.ivr_self_serve_payment_flag, false)) AS paid,
               coalesce(h.payment_amount, 0) AS payment_amount,
               (coalesce(h.link_clicked_flag, false) OR coalesce(h.email_clicked_flag, false)) AS clicked,
               coalesce(h.callback_requested_flag, false) AS callback,
               coalesce(h.hardship_mentioned_flag, false) AS hardship_mentioned,
               coalesce(h.dispute_raised_flag, false) AS dispute_raised,
               h.contact_hour_local
        FROM gold.contact_timeline t
        JOIN bronze.contact_history h ON h.contact_id = t.contact_id
        WHERE t.case_id IS NOT NULL AND t.contact_ts_utc IS NOT NULL
    """,
    "_p3_bureau": """
        SELECT x.golden_id, b.pull_date, b.risk_score, b.revolving_utilisation AS utilisation,
               b.delinquent_trades_count AS delinquent_trades, b.inquiries_hard_6m
        FROM bronze.bureau_history b
        JOIN gold.customer_xref x ON x.source_system = 'core_banking' AND x.source_key = b.bank_subject_ref
        WHERE b.risk_score IS NOT NULL
        UNION ALL
        SELECT x.golden_id, e.pull_date, e.risk_score, e.revolving_utilisation,
               e.off_us_delinquent_trades, e.inquiries_hard_6m
        FROM bronze.external e
        JOIN gold.customer_xref x ON x.source_system = 'core_banking' AND x.source_key = e.bank_subject_ref
        WHERE e.risk_score IS NOT NULL
    """,
    "_p3_salary": """
        SELECT x.golden_id, strptime(s.credit_month || '-01', '%Y-%m-%d')::DATE AS month_start,
               max(coalesce(s.gap_flag, false)::INT) AS gap, sum(coalesce(s.credit_amount_total, 0)) AS amount,
               max((s.employer_flag = 'Y')::INT) AS payroll
        FROM bronze.salary_credit_history s
        JOIN gold.customer_xref x ON x.source_system = 'crm' AND x.source_key = s.crm_customer_id
        GROUP BY 1, 2
    """,
    # month_end_date arrives as ISO, MM/DD/YYYY and YYYYMMDD; month-end days (>= 28) make it unambiguous
    "_p3_accounts": """
        WITH a AS (
            SELECT crm_customer_id,
                   coalesce(try_strptime(month_end_date::VARCHAR, '%Y-%m-%d'),
                            try_strptime(month_end_date::VARCHAR, '%Y%m%d'),
                            try_strptime(month_end_date::VARCHAR, '%m/%d/%Y'),
                            try_strptime(month_end_date::VARCHAR, '%d/%m/%Y'))::DATE AS month_end,
                   coalesce(balance, 0) AS balance, coalesce(limit_or_original_amount, 0) AS lim,
                   coalesce(minimum_due, 0) AS minimum_due, coalesce(payment_made, 0) AS payment_made,
                   coalesce(dpd, 0) AS dpd, coalesce(overlimit_flag, false) AS overlimit
            FROM bronze.account_monthly_snapshot
        )
        SELECT x.golden_id, a.month_end, sum(a.balance) AS balance, sum(a.lim) AS lim, max(a.dpd) AS max_dpd,
               bool_and(a.minimum_due <= 0 OR a.payment_made >= a.minimum_due) AS min_paid,
               bool_or(a.overlimit) AS overlimit
        FROM a JOIN gold.customer_xref x ON x.source_system = 'crm' AND x.source_key = a.crm_customer_id
        WHERE a.month_end IS NOT NULL
        GROUP BY 1, 2
    """,
}

FEATURE_SQL = """
WITH pop AS (
    SELECT c.case_id, c.golden_id, c.crm_customer_id, c.case_open_date,
           (DATE '{as_of}' - c.case_open_date)::INT AS age,
           coalesce(c.entry_overdue, 0) AS entry_overdue,
           coalesce(c.prior_cases_12m, 0) AS prior_cases_12m,
           {product_case} AS product_code,
           {reason_case} AS open_reason_code,
           -- overdue at the latest trajectory milestone the case has reached by as_of
           coalesce(
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 90 THEN c.overdue_at_day_90 END,
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 60 THEN c.overdue_at_day_60 END,
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 45 THEN c.overdue_at_day_45 END,
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 30 THEN c.overdue_at_day_30 END,
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 21 THEN c.overdue_at_day_21 END,
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 14 THEN c.overdue_at_day_14 END,
               CASE WHEN (DATE '{as_of}' - c.case_open_date) >= 7  THEN c.overdue_at_day_7 END,
               c.entry_overdue, 0) AS overdue_now
    FROM gold.case_360 c
    WHERE c.case_open_date <= DATE '{as_of}'
      AND (c.outcome_date IS NULL OR c.outcome_date > DATE '{as_of}')
      AND (c.cure_date IS NULL OR c.cure_date > DATE '{as_of}')
),
others AS (
    SELECT p.case_id, count(o.case_id) AS other_open_cases
    FROM pop p
    JOIN gold.case_360 o ON o.golden_id = p.golden_id AND o.case_id <> p.case_id
     AND o.case_open_date <= DATE '{as_of}'
     AND (o.outcome_date IS NULL OR o.outcome_date > DATE '{as_of}')
    GROUP BY 1
),
ct AS (
    -- as_of means the start of that day: labels count contacts from as_of 00:00 on, features stop before it
    SELECT c.*, (DATE '{as_of}' - c.contact_ts_utc::DATE)::INT - 1 AS ago
    FROM _p3_contacts c
    WHERE c.contact_ts_utc < DATE '{as_of}'
      AND c.case_id IN (SELECT case_id FROM pop)
),
contacts AS (
    SELECT case_id,
           count(*) AS contacts_total,
           count(*) FILTER (WHERE ago < 7) AS contacts_7d,
           count(*) FILTER (WHERE ago < 30) AS contacts_30d,
           count(*) FILTER (WHERE ago < 30 AND direction = 'inbound') AS inbound_30d,
           count(*) FILTER (WHERE ago < 30 AND rpc_flag) AS rpc_30d,
           min(ago) AS days_since_last_contact,
           min(ago) FILTER (WHERE rpc_flag) AS days_since_last_rpc,
           count(*) FILTER (WHERE paid) AS payments_total,
           count(*) FILTER (WHERE paid AND ago < 30) AS payments_30d,
           sum(payment_amount) FILTER (WHERE paid AND ago < 90) AS payment_amount_90d,
           min(ago) FILTER (WHERE paid) AS days_since_last_payment,
           count(*) FILTER (WHERE clicked AND ago < 30) AS link_clicks_30d,
           count(*) FILTER (WHERE callback AND ago < 30) AS callback_requested_30d,
           bool_or(hardship_mentioned)::INT AS hardship_mentioned_any,
           bool_or(dispute_raised)::INT AS dispute_raised_any
    FROM ct GROUP BY 1
),
best_hour AS (   -- hour with the most right-party contacts; ties go to the earlier hour (repeatable)
    SELECT case_id, contact_hour_local AS best_rpc_hour
    FROM (SELECT case_id, contact_hour_local, count(*) AS n FROM ct
          WHERE rpc_flag AND contact_hour_local IS NOT NULL GROUP BY 1, 2)
    QUALIFY row_number() OVER (PARTITION BY case_id ORDER BY n DESC, contact_hour_local) = 1
),
bureau AS (
    SELECT b.golden_id, b.risk_score, b.utilisation, b.delinquent_trades, b.inquiries_hard_6m,
           (DATE '{as_of}' - b.pull_date)::INT AS bureau_age_days
    FROM _p3_bureau b
    WHERE b.pull_date <= DATE '{as_of}' AND b.golden_id IN (SELECT golden_id FROM pop)
    -- same-day pulls from two sources: break the tie on values so every run picks the same one
    QUALIFY row_number() OVER (PARTITION BY b.golden_id ORDER BY b.pull_date DESC, b.risk_score, b.utilisation,
                                                               b.delinquent_trades, b.inquiries_hard_6m) = 1
),
salary AS (
    SELECT golden_id,
           sum(gap) FILTER (WHERE month_start >= date_trunc('month', DATE '{as_of}') - INTERVAL 3 MONTH) AS gap3,
           avg(amount) FILTER (WHERE month_start >= date_trunc('month', DATE '{as_of}') - INTERVAL 3 MONTH) AS recent,
           avg(amount) FILTER (WHERE month_start < date_trunc('month', DATE '{as_of}') - INTERVAL 3 MONTH) AS prior,
           max(payroll) AS has_payroll
    FROM _p3_salary
    WHERE month_start < date_trunc('month', DATE '{as_of}')
      AND month_start >= date_trunc('month', DATE '{as_of}') - INTERVAL 9 MONTH
      AND golden_id IN (SELECT golden_id FROM pop)
    GROUP BY 1
),
acct_months AS (
    SELECT *, row_number() OVER (PARTITION BY golden_id ORDER BY month_end DESC) AS rk
    FROM _p3_accounts
    WHERE month_end <= DATE '{as_of}' - INTERVAL 60 DAY
      AND month_end > DATE '{as_of}' - INTERVAL 270 DAY
      AND golden_id IN (SELECT golden_id FROM pop)
),
accounts AS (
    SELECT golden_id,
           count(*) FILTER (WHERE rk <= 6 AND min_paid) AS acct_months_min_paid_6m,
           max(CASE WHEN rk = 1 AND lim > 0 THEN balance / lim END) AS acct_utilisation,
           max(CASE WHEN rk = 1 THEN max_dpd END) AS acct_max_dpd,
           max(CASE WHEN rk = 1 THEN overlimit::INT END) AS acct_overlimit
    FROM acct_months WHERE rk <= 6 GROUP BY 1
)
SELECT p.case_id, p.golden_id, p.crm_customer_id, DATE '{as_of}' AS as_of_date,
       p.entry_overdue, p.prior_cases_12m, p.product_code, p.open_reason_code,
       p.age AS case_age_days, p.overdue_now,
       CASE WHEN p.entry_overdue > 0 THEN (p.overdue_now - p.entry_overdue) / p.entry_overdue ELSE 0 END
           AS overdue_growth_pct,
       coalesce(o.other_open_cases, 0) AS other_open_cases,
       coalesce(c.contacts_total, 0) AS contacts_total,
       coalesce(c.contacts_7d, 0) AS contacts_7d,
       coalesce(c.contacts_30d, 0) AS contacts_30d,
       coalesce(c.inbound_30d, 0) AS inbound_30d,
       coalesce(c.rpc_30d, 0) AS rpc_30d,
       CASE WHEN coalesce(c.contacts_30d, 0) > 0 THEN c.rpc_30d / c.contacts_30d ELSE 0 END AS rpc_rate_30d,
       coalesce(c.days_since_last_contact, 999) AS days_since_last_contact,
       coalesce(c.days_since_last_rpc, 999) AS days_since_last_rpc,
       coalesce(c.payments_total, 0) AS payments_total,
       coalesce(c.payments_30d, 0) AS payments_30d,
       coalesce(c.payment_amount_90d, 0) AS payment_amount_90d,
       coalesce(c.days_since_last_payment, 999) AS days_since_last_payment,
       coalesce(c.link_clicks_30d, 0) AS link_clicks_30d,
       coalesce(c.callback_requested_30d, 0) AS callback_requested_30d,
       coalesce(c.hardship_mentioned_any, 0) AS hardship_mentioned_any,
       coalesce(c.dispute_raised_any, 0) AS dispute_raised_any,
       b.risk_score AS bureau_score,
       b.utilisation AS bureau_utilisation,
       b.delinquent_trades AS bureau_delinquent_trades,
       b.inquiries_hard_6m AS bureau_inquiries_6m,
       b.bureau_age_days,
       coalesce(s.gap3, 0) AS salary_gap_months_3m,
       CASE WHEN s.prior > 0 THEN (s.recent - s.prior) / s.prior END AS salary_drop_pct,
       coalesce(s.has_payroll, 0) AS has_payroll,
       a.acct_months_min_paid_6m, a.acct_utilisation, a.acct_max_dpd, a.acct_overlimit,
       h.best_rpc_hour
FROM pop p
LEFT JOIN others o ON o.case_id = p.case_id
LEFT JOIN contacts c ON c.case_id = p.case_id
LEFT JOIN best_hour h ON h.case_id = p.case_id
LEFT JOIN bureau b ON b.golden_id = p.golden_id
LEFT JOIN salary s ON s.golden_id = p.golden_id
LEFT JOIN accounts a ON a.golden_id = p.golden_id
"""


def _code_case(column: str, codes: dict[str, int]) -> str:
    whens = " ".join(f"WHEN '{k}' THEN {v}" for k, v in codes.items())
    return f"CASE c.{column} {whens} ELSE 0 END"


def _prepare(con) -> None:
    """Create the per-connection TEMP helper tables once."""
    have = {r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE temporary").fetchall()}
    for name, sql in _PREPARE.items():
        if name not in have:
            con.execute(f"CREATE TEMP TABLE {name} AS {sql}")


def feature_sql(as_of_date: str | dt.date) -> str:
    as_of = dt.date.fromisoformat(str(as_of_date)[:10]).isoformat()  # validates the date
    return FEATURE_SQL.format(as_of=as_of,
                              product_case=_code_case("primary_product", PRODUCT_CODES),
                              reason_case=_code_case("case_open_reason", OPEN_REASON_CODES))


def build_case_features(con, as_of_date: str | dt.date) -> int:
    """Build point-in-time features for every case open at ``as_of_date`` into features.case_features.

    Use a past date for training and ``config.SNAPSHOT_DATE`` for live scoring. Rows of other dates are
    kept, so several training dates stack in one table. Returns the number of rows written.
    """
    as_of = dt.date.fromisoformat(str(as_of_date)[:10]).isoformat()
    _prepare(con)
    sql = feature_sql(as_of)

    cols = [d[0] for d in con.execute(f"DESCRIBE {sql}").fetchall()]
    leaked = (set(cols) & OUTCOME_COLUMNS) | (set(cols) & config.PROTECTED_COLUMNS)
    if leaked:
        raise RuntimeError(f"Outcome or protected columns in features: {sorted(leaked)}")
    expected = KEYS + FEATURE_COLUMNS + INFO_COLUMNS
    if sorted(cols) != sorted(expected):
        raise RuntimeError(f"Feature columns differ from FEATURE_COLUMNS: {sorted(set(cols) ^ set(expected))}")

    con.execute("CREATE SCHEMA IF NOT EXISTS features")
    exists = con.execute("SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'features' "
                         "AND table_name = 'case_features'").fetchone()[0]
    if exists:
        existing = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
        if existing != cols:  # older layout: start again
            con.execute(f"DROP TABLE {TABLE}")
            exists = 0
    if exists:
        con.execute(f"DELETE FROM {TABLE} WHERE as_of_date = DATE '{as_of}'")
        con.execute(f"INSERT INTO {TABLE} {sql}")
    else:
        con.execute(f"CREATE TABLE {TABLE} AS {sql}")

    n = con.execute(f"SELECT count(*) FROM {TABLE} WHERE as_of_date = DATE '{as_of}'").fetchone()[0]
    print(f"{TABLE}  {n:>9,d} rows  (as_of={as_of})", flush=True)
    return n


if __name__ == "__main__":
    from ontrack.db import connect
    con = connect()
    build_case_features(con, config.SNAPSHOT_DATE)
    con.close()
