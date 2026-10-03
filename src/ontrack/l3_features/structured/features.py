"""Structured case features for Layer 4 (owner: P3).

One function ``build_case_features(con, as_of_date)`` builds features for
both training (past date) and live scoring (snapshot date).  Every feature
is point-in-time correct: only data available on or before *as_of_date* is
used.

Writes ``features.case_features`` with columns:
  case_id, golden_id, as_of_date, <feature columns>

Outcome columns and PROTECTED_COLUMNS are never included.
"""
from __future__ import annotations

import datetime as dt

from ontrack import config

FEATURE_SQL = """
WITH open_cases AS (
    SELECT
        cs.case_id,
        cs.golden_id,
        cs.crm_customer_id,
        cs.case_open_date,
        cs.treatment_stage,
        cs.dpd_at_entry,
        cs.assigned_agent_id
    FROM gold.case_360 cs
    WHERE cs.case_open_date <= '{as_of}'
),

-- Delinquency features: current DPD, max, trend
delinquency AS (
    SELECT
        a.golden_id,
        max(coalesce(a.dpd, 0)) AS dpd_current,
        max(coalesce(a.past_due_amount, 0)) AS past_due_max,
        count(*) AS n_accounts,
        sum(CASE WHEN coalesce(a.dpd, 0) >= 30 THEN 1 ELSE 0 END) AS accounts_30dpd,
        max(coalesce(a.balance, 0)) AS max_balance,
        sum(coalesce(a.balance, 0)) AS total_balance,
        sum(coalesce(a.past_due_amount, 0)) AS total_past_due,
        CASE WHEN sum(coalesce(a.balance, 0)) > 0
             THEN sum(coalesce(a.past_due_amount, 0)) / sum(coalesce(a.balance, 0))
             ELSE 0 END AS past_due_ratio
    FROM gold.c360_account a
    GROUP BY a.golden_id
),

-- Payment behaviour from contact timeline
payment AS (
    SELECT
        ct.case_id,
        ct.golden_id,
        count(*) FILTER (WHERE ct.payment_taken_flag) AS payments_total,
        count(*) FILTER (
            WHERE ct.payment_taken_flag
            AND ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '90 days')
        ) AS payments_90d,
        count(*) FILTER (
            WHERE ct.payment_taken_flag
            AND ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '30 days')
        ) AS payments_30d,
        min(CASE WHEN ct.payment_taken_flag
            THEN DATE '{as_of}' - ct.contact_ts_utc::DATE END)::INT AS days_since_last_payment
    FROM gold.contact_timeline ct
    WHERE ct.contact_ts_utc <= TIMESTAMP '{as_of} 23:59:59'
    GROUP BY ct.case_id, ct.golden_id
),

-- Contact response features
contacts AS (
    SELECT
        ct.case_id,
        ct.golden_id,
        count(*) AS total_contacts,
        count(*) FILTER (WHERE ct.rpc_flag) AS rpc_count,
        count(*) FILTER (
            WHERE ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '30 days')
        ) AS contacts_30d,
        count(*) FILTER (
            WHERE ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '7 days')
        ) AS contacts_7d,
        count(*) FILTER (
            WHERE ct.rpc_flag
            AND ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '30 days')
        ) AS rpc_30d,
        CASE WHEN count(*) FILTER (
            WHERE ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '30 days')
        ) > 0
        THEN count(*) FILTER (
            WHERE ct.rpc_flag
            AND ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '30 days')
        )::FLOAT / count(*) FILTER (
            WHERE ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '30 days')
        )
        ELSE 0 END AS rpc_rate_30d,
        mode() WITHIN GROUP (ORDER BY extract(hour FROM ct.contact_ts_utc))
            FILTER (WHERE ct.rpc_flag) AS best_rpc_hour,
        list(DISTINCT ct.channel) FILTER (
            WHERE ct.contact_ts_utc >= (DATE '{as_of}' - INTERVAL '90 days')
        ) AS channels_used_90d
    FROM gold.contact_timeline ct
    WHERE ct.contact_ts_utc <= TIMESTAMP '{as_of} 23:59:59'
    GROUP BY ct.case_id, ct.golden_id
),

-- Case-level features
case_feats AS (
    SELECT
        oc.case_id,
        oc.golden_id,
        (DATE '{as_of}' - oc.case_open_date::DATE)::INT AS case_age_days,
        oc.treatment_stage,
        coalesce(oc.dpd_at_entry, 0) AS dpd_at_entry
    FROM open_cases oc
),

-- Bureau / external score features (latest pull per golden_id)
bureau AS (
    SELECT
        x.golden_id,
        e.risk_score AS bureau_score_current,
        e.risk_score_delta_90d AS score_delta_90d,
        e.inquiries_hard_3m,
        coalesce(e.utilisation_m01, 0) AS utilisation_current,
        coalesce(e.utilisation_m01, 0) - coalesce(e.utilisation_m06, 0) AS utilisation_trend_6m
    FROM bronze.external e
    JOIN gold.customer_xref x ON x.source_system = 'core_banking' AND x.source_key = e.bank_subject_ref
    QUALIFY row_number() OVER (PARTITION BY x.golden_id ORDER BY e.pull_date DESC) = 1
),

-- Customer-level flags (non-protected)
customer AS (
    SELECT
        cu.golden_id,
        cu.products_held,
        cu.total_exposure,
        cu.total_overdue,
        cu.max_dpd,
        cu.open_case_count,
        cu.consent_call,
        cu.consent_sms,
        cu.consent_email,
        cu.consent_push
    FROM gold.c360_customer cu
)

SELECT
    cf.case_id,
    cf.golden_id,
    DATE '{as_of}' AS as_of_date,

    -- Case-level
    cf.case_age_days,
    cf.treatment_stage,
    cf.dpd_at_entry,

    -- Delinquency
    coalesce(d.dpd_current, 0) AS dpd_current,
    coalesce(d.past_due_max, 0) AS past_due_max,
    coalesce(d.n_accounts, 0) AS n_accounts,
    coalesce(d.accounts_30dpd, 0) AS accounts_30dpd,
    coalesce(d.total_balance, 0) AS total_balance,
    coalesce(d.total_past_due, 0) AS total_past_due,
    coalesce(d.past_due_ratio, 0) AS past_due_ratio,

    -- Payment behaviour
    coalesce(p.payments_total, 0) AS payments_total,
    coalesce(p.payments_90d, 0) AS payments_90d,
    coalesce(p.payments_30d, 0) AS payments_30d,
    coalesce(p.days_since_last_payment, 999) AS days_since_last_payment,

    -- Contact response
    coalesce(ct.total_contacts, 0) AS total_contacts,
    coalesce(ct.rpc_count, 0) AS rpc_count,
    coalesce(ct.contacts_30d, 0) AS contacts_30d,
    coalesce(ct.contacts_7d, 0) AS contacts_7d,
    coalesce(ct.rpc_30d, 0) AS rpc_30d,
    coalesce(ct.rpc_rate_30d, 0) AS rpc_rate_30d,
    ct.best_rpc_hour,

    -- Bureau / external
    b.bureau_score_current,
    coalesce(b.score_delta_90d, 0) AS score_delta_90d,
    coalesce(b.inquiries_hard_3m, 0) AS inquiries_hard_3m,
    coalesce(b.utilisation_current, 0) AS utilisation_current,
    coalesce(b.utilisation_trend_6m, 0) AS utilisation_trend_6m,

    -- Customer-level
    coalesce(cu.products_held, 0) AS products_held,
    coalesce(cu.total_exposure, 0) AS total_exposure,
    coalesce(cu.total_overdue, 0) AS total_overdue,
    coalesce(cu.open_case_count, 0) AS open_case_count

FROM case_feats cf
LEFT JOIN delinquency d ON d.golden_id = cf.golden_id
LEFT JOIN payment p ON p.case_id = cf.case_id AND p.golden_id = cf.golden_id
LEFT JOIN contacts ct ON ct.case_id = cf.case_id AND ct.golden_id = cf.golden_id
LEFT JOIN bureau b ON b.golden_id = cf.golden_id
LEFT JOIN customer cu ON cu.golden_id = cf.golden_id
"""

OUTCOME_COLUMNS = frozenset({
    "cure_flag", "days_to_cure", "outcome", "dpd_at_day_30", "dpd_at_day_60",
    "dpd_at_day_90", "resolution_date", "resolution_type",
})

FEATURE_COLUMNS: list[str] = []


def build_case_features(con, as_of_date: str | dt.date) -> int:
    """Build case features and write to features.case_features.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
    as_of_date : str or date
        The point-in-time date. Use a past date for training, the snapshot
        date for live scoring.

    Returns
    -------
    int
        Number of rows written.
    """
    as_of = str(as_of_date)
    sql = FEATURE_SQL.replace("{as_of}", as_of)

    con.execute(f"CREATE OR REPLACE TABLE features.case_features AS {sql}")

    # Verify no outcome or protected columns leaked
    cols = [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'features' AND table_name = 'case_features'"
    ).fetchall()]

    leaked_outcome = set(cols) & OUTCOME_COLUMNS
    if leaked_outcome:
        raise RuntimeError(f"Outcome columns in features: {leaked_outcome}")

    leaked_protected = set(cols) & config.PROTECTED_COLUMNS
    if leaked_protected:
        raise RuntimeError(f"Protected columns in features: {leaked_protected}")

    global FEATURE_COLUMNS
    FEATURE_COLUMNS = [c for c in cols if c not in ("case_id", "golden_id", "as_of_date")]

    n = con.execute("SELECT count(*) FROM features.case_features").fetchone()[0]
    print(f"features.case_features  {n:>12,d} rows  (as_of={as_of})", flush=True)
    return n


if __name__ == "__main__":
    from ontrack.db import connect
    con = connect()
    build_case_features(con, config.SNAPSHOT_DATE)
    con.close()
