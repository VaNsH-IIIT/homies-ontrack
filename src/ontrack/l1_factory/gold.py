"""Gold: Collections 360 data products (owner: P1). Column names follow README "Interfaces between parts".

Conservative rules when a person has more than one CRM record:
  consent_* is true only if every record allows it; holds (do-not-call, cease, insolvency,
  deceased, third party) apply if any record has one.
Protected attributes never enter gold (they stay in bronze for fairness testing only).
"""
from ontrack import config
from ontrack.db import connect

STEPS = {
    "c360_account": """
        SELECT a.card_account_id AS account_id, x.golden_id, 'card' AS product_type,
               a.current_balance AS balance, a.credit_limit, a.past_due_amount, a.dpd, a.dpd_bucket,
               a.account_status, a.snapshot_date
        FROM silver.card_accounts a
        JOIN gold.customer_xref x ON x.source_system = 'cards' AND x.source_key = a.src_customer_ref
        UNION ALL
        SELECT l.loan_id, x.golden_id, coalesce(l.product_type, 'loan'), l.total_outstanding, NULL,
               l.past_due_amount, l.dpd, l.dpd_bucket, NULL, l.snapshot_date
        FROM silver.loan_accounts l
        JOIN gold.customer_xref x ON x.source_system = 'loans' AND x.source_key = l.src_customer_ref
        UNION ALL
        SELECT d.deposit_account_id, x.golden_id, coalesce(d.product_type, 'deposit'), d.current_balance,
               d.overdraft_limit, NULL, d.overdraft_dpd, d.overdraft_dpd_bucket, d.account_status, d.snapshot_date
        FROM silver.deposit_accounts d
        JOIN gold.customer_xref x ON x.source_system = 'core_banking' AND x.source_key = d.src_customer_ref
    """,
    "case_360": """
        SELECT x.golden_id, c.coll_customer_ref AS crm_customer_id, c.*
        FROM bronze.collections_cases c
        LEFT JOIN gold.customer_xref x ON x.source_system = 'crm' AND x.source_key = c.coll_customer_ref
    """,
    "contact_timeline": """
        SELECT x.golden_id, h.case_id, h.contact_id, h.crm_customer_id, h.account_id, h.contact_ts_utc,
               coalesce(h.channel, h.channel_v2) AS channel, h.direction, h.outcome_code, h.rpc_flag,
               h.payment_taken_flag, h.note_id, h.transcript_id
        FROM bronze.contact_history h
        LEFT JOIN gold.customer_xref x ON x.source_system = 'crm' AND x.source_key = h.crm_customer_id
    """,
    "c360_customer": """
        WITH crm AS (
            SELECT x.golden_id, c.*,
                   row_number() OVER (PARTITION BY x.golden_id
                                      ORDER BY (c.duplicate_of_crm_id IS NULL) DESC, c.last_profile_update_ts DESC) AS rk
            FROM silver.crm c
            JOIN gold.customer_xref x ON x.source_system = 'crm' AND x.source_key = c.crm_customer_id
        ),
        flags AS (
            SELECT golden_id,
                   bool_and(coalesce(consent_call, false))       AS consent_call,
                   bool_and(coalesce(consent_sms, false))        AS consent_sms,
                   bool_and(coalesce(consent_email, false))      AS consent_email,
                   bool_and(coalesce(consent_push, false))       AS consent_push,
                   bool_and(coalesce(consent_autodialer, false)) AS consent_autodialer,
                   bool_or(coalesce(internal_do_not_call_flag, false)) AS internal_do_not_call_flag,
                   bool_or(coalesce(cease_communication_flag, false))  AS cease_communication_flag,
                   bool_or(coalesce(bankruptcy_flag, false) OR coalesce(consumer_proposal_flag, false)) AS insolvency_flag,
                   bool_or(coalesce(deceased_flag, false))       AS deceased_flag,
                   bool_or(coalesce(third_party_authorised_flag, false) OR coalesce(power_of_attorney_flag, false)
                           OR coalesce(legal_representative_flag, false) OR coalesce(credit_counselling_agency_flag, false))
                                                                 AS third_party_hold_flag,
                   bool_or(coalesce(vulnerability_flag, false))  AS vulnerability_flag,
                   count(*) AS crm_record_count
            FROM crm GROUP BY golden_id
        ),
        accts AS (
            SELECT golden_id, count(*) AS products_held,
                   sum(CASE WHEN product_type = 'card' OR product_type NOT IN ('chequing', 'savings', 'tfsa', 'usd', 'deposit')
                            THEN greatest(coalesce(balance, 0), 0) ELSE 0 END) AS total_exposure,
                   sum(coalesce(past_due_amount, 0)) AS total_overdue,
                   max(coalesce(dpd, 0)) AS max_dpd
            FROM gold.c360_account GROUP BY golden_id
        ),
        cases AS (
            SELECT golden_id, count(*) FILTER (WHERE outcome IS NULL) AS open_case_count, count(*) AS case_count
            FROM gold.case_360 WHERE golden_id IS NOT NULL GROUP BY golden_id
        ),
        xref AS (
            SELECT golden_id, min(match_confidence) AS match_confidence_min,
                   list(DISTINCT source_system ORDER BY source_system) AS _source_systems,
                   count(*) AS source_key_count
            FROM gold.customer_xref GROUP BY golden_id
        )
        SELECT x.golden_id,
               p.crm_customer_id AS primary_crm_customer_id,
               p.province_code, p.time_zone, p.preferred_language,
               f.* EXCLUDE (golden_id),
               coalesce(a.products_held, 0) AS products_held,
               coalesce(a.total_exposure, 0) AS total_exposure,
               coalesce(a.total_overdue, 0) AS total_overdue,
               coalesce(a.max_dpd, 0) AS max_dpd,
               coalesce(k.open_case_count, 0) AS open_case_count,
               coalesce(k.case_count, 0) AS case_count,
               x.match_confidence_min, x.source_key_count, x._source_systems,
               now() AS _loaded_at,
               CASE WHEN x.match_confidence_min < 0.95 THEN 'review_match' ELSE 'ok' END AS _dq_status
        FROM xref x
        LEFT JOIN crm p ON p.golden_id = x.golden_id AND p.rk = 1
        LEFT JOIN flags f ON f.golden_id = x.golden_id
        LEFT JOIN accts a ON a.golden_id = x.golden_id
        LEFT JOIN cases k ON k.golden_id = x.golden_id
    """,
}


def main() -> None:
    con = connect()
    for name, sql in STEPS.items():
        con.execute(f"CREATE OR REPLACE TABLE gold.{name} AS {sql}")
        n = con.execute(f"SELECT count(*) FROM gold.{name}").fetchone()[0]
        print(f"gold.{name:18s} {n:>12,d} rows", flush=True)
    # Guard: no protected attribute may reach gold.
    leaked = con.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'gold' "
        f"AND column_name IN ({', '.join(repr(c) for c in sorted(config.PROTECTED_COLUMNS))})").fetchall()
    if leaked:
        raise RuntimeError(f"Protected attributes found in gold: {leaked}")
    con.close()


if __name__ == "__main__":
    main()
