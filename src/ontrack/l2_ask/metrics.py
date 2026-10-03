"""Certified metrics as templated SQL (owner: P2).

Design, Layer 2 step 3: a certified metric is expanded from its stored definition, so the same question always
gives the same number. metric_definitions holds the business formula in words; each template below is the
executable version of that row (formula, grain, time basis, default filters), with a fixed set of group-by
dimensions. The LLM (or the rule parser) only chooses metric, window and grouping; it never writes this SQL.

    sql = certified_sql("average_dpd", group_by="queue")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RESOLVED = "('kept','partially_kept','broken')"
CHANNEL = "coalesce(h.channel_v2, h.channel)"


@dataclass
class Metric:
    metric_id: str
    source: str                       # FROM ... (with joins)
    values: list[tuple[str, str]]     # (column name, aggregate expression)
    count_name: str                   # name of the row-count column
    count_expr: str = "count(*)"
    date_col: str | None = None       # time basis column; window filters apply to it
    where: list[str] = field(default_factory=list)   # default filters
    dims: dict[str, str] = field(default_factory=dict)  # group-by name -> expression
    note: str = ""


def _pct(cond: str, dec: int = 1) -> str:
    return f"round(100.0 * avg(CASE WHEN {cond} THEN 1 ELSE 0 END), {dec})"


PROMISE_SOURCE = ("bronze.promises_to_pay p LEFT JOIN bronze.agents a ON a.agent_id = p.agent_id "
                  "LEFT JOIN bronze.collections_cases c ON c.case_id = p.case_id")
PROMISE_DIMS = {
    "site": "coalesce(a.site, 'self_serve')", "agent_site": "coalesce(a.site, 'self_serve')",
    "prior_broken": "least(p.prior_broken_ptp_count, 3)", "test_cell": "c.test_cell", "queue": "c.queue",
    "product": "p.product", "ptp_channel": "p.ptp_channel", "channel": "p.ptp_channel",
    "month": "strftime(p.ptp_due_date, '%Y-%m')", "current_bucket": "c.current_bucket",
    "primary_product": "c.primary_product", "province_code": "c.province_code",
}
CONTACT_DIMS = {
    "channel": CHANNEL, "contact_hour_local": "h.contact_hour_local", "hour": "h.contact_hour_local",
    "agent_site": "h.agent_site", "site": "h.agent_site", "day": "CAST(h.contact_ts_local AS DATE)",
    "date": "CAST(h.contact_ts_local AS DATE)", "month": "strftime(h.contact_ts_local, '%Y-%m')",
    "day_of_week": "h.day_of_week", "dialer_mode": "h.dialer_mode", "test_cell": "h.test_cell",
    "bucket_at_contact": "h.bucket_at_contact", "direction": "h.direction",
}
CASE_DIMS = {
    "queue": "queue", "current_bucket": "current_bucket", "primary_product": "primary_product",
    "product": "primary_product", "province_code": "province_code", "province": "province_code",
    "assigned_team": "assigned_team", "test_cell": "test_cell", "strategy_code": "strategy_code",
    "month": "strftime(case_open_date, '%Y-%m')", "case_open_reason": "case_open_reason",
    "language_of_service": "language_of_service",
}

METRICS: dict[str, Metric] = {m.metric_id: m for m in [
    Metric("promise_kept_rate", PROMISE_SOURCE, [("kept_pct", _pct("p.ptp_status = 'kept'"))], "promises",
           date_col="p.ptp_due_date", where=[f"p.ptp_status IN {RESOLVED}"], dims=PROMISE_DIMS),
    Metric("broken_promise_rate", PROMISE_SOURCE, [("broken_rate_pct", _pct("p.ptp_status = 'broken'"))], "promises",
           date_col="p.ptp_due_date", where=[f"p.ptp_status IN {RESOLVED}"], dims=PROMISE_DIMS),
    Metric("rpc_rate", "bronze.contact_history h", [("rpc_rate_pct", _pct("h.rpc_flag"))], "attempts",
           date_col="h.contact_ts_local", where=[f"{CHANNEL} = 'call'", "h.direction = 'outbound'"],
           dims=CONTACT_DIMS),
    Metric("ptp_rate", "bronze.contact_history h", [("ptp_rate_pct", _pct("h.ptp_made_flag"))], "rpcs",
           date_col="h.contact_ts_local", where=["h.rpc_flag"], dims=CONTACT_DIMS),
    Metric("cost_per_contact", "bronze.contact_history h",
           [("cost_per_contact_cad", "round(sum(h.contact_cost_cad) / count(h.contact_id), 2)")], "contacts",
           date_col="h.contact_ts_local", where=[f"{CHANNEL} <> 'system'"], dims=CONTACT_DIMS),
    Metric("cost_per_rpc", "bronze.contact_history h",
           [("cost_per_rpc_cad", "round(sum(h.contact_cost_cad) / nullif(count(*) FILTER (WHERE h.rpc_flag), 0), 2)")],
           "contacts", date_col="h.contact_ts_local", where=[f"{CHANNEL} <> 'system'"], dims=CONTACT_DIMS),
    Metric("hardship_rate", "bronze.collections_cases", [("hardship_rate_pct", _pct("hardship_flag"))], "cases",
           date_col="case_open_date", dims=CASE_DIMS),
    Metric("average_dpd", "bronze.collections_cases", [("avg_dpd", "round(avg(current_dpd), 1)")], "open_cases",
           where=["outcome IS NULL"], dims=CASE_DIMS),
    Metric("cure_rate", "bronze.collections_cases",
           [("cure_rate_pct", _pct("cure_flag AND days_to_cure <= 30", 2))], "cases",
           date_col="case_open_date",
           where=["NOT coalesce(insolvency_hold_flag, false)", "NOT coalesce(deceased_hold_flag, false)"],
           dims=CASE_DIMS, note="cohort form: cases opened in the window that cured within 30 days of opening"),
    Metric("contact_attempts_per_case",
           "bronze.contact_history h JOIN bronze.collections_cases c ON c.case_id = h.case_id",
           [("attempts_per_case", "round(count(*) / count(DISTINCT h.case_id), 2)")], "cases",
           count_expr="count(DISTINCT h.case_id)", date_col="h.contact_ts_local",
           where=["h.direction = 'outbound'", f"{CHANNEL} <> 'system'"],
           dims={"current_bucket": "c.current_bucket", "queue": "c.queue", "primary_product": "c.primary_product",
                 "channel": CHANNEL, "province_code": "c.province_code"}),
    Metric("delinquency_rate", "bronze.card_accounts",
           [("delinquency_rate_pct", _pct("dpd >= 1", 2))], "accounts",
           where=["snapshot_date = (SELECT max(snapshot_date) FROM bronze.card_accounts)",
                  "account_status IN ('active','blocked')", "dpd IS NOT NULL"],
           dims={"product_code": "product_code", "product": "product_code", "card_tier": "card_tier",
                 "card_network": "card_network"}),
    Metric("collected_amount", "bronze.promises_to_pay p",
           [("amount_paid_cad", "round(sum(p.amount_paid_against), 2)")], "promises_paid",
           count_expr="count(*) FILTER (WHERE p.amount_paid_against > 0)", date_col="p.paid_date",
           dims={"product": "p.product", "channel": "p.ptp_channel", "month": "strftime(p.paid_date, '%Y-%m')"},
           note="payments recorded against promises, by payment date"),
    # Not in metric_definitions (so not "certified"), but a plain count with the same open-case rule.
    Metric("open_case_count", "bronze.collections_cases", [], "open_cases", where=["outcome IS NULL"],
           dims=CASE_DIMS, note="count of open cases (outcome IS NULL); uncertified helper"),
    Metric("payroll_delay_share", "bronze.deposit_accounts",
           [("payroll_delay_pct", _pct("payroll_delay_days > 7", 2))], "accounts",
           where=["snapshot_date = (SELECT max(snapshot_date) FROM bronze.deposit_accounts)", "payroll_deposit_flag"],
           dims={"product_type": "product_type"}),
]}


def certified_sql(metric_id: str, start: str | None = None, end: str | None = None, group_by: str | None = None,
                  extra_where: list[str] | None = None) -> str:
    """SQL for a certified metric. start/end are ISO dates (end inclusive) on the metric's time basis."""
    m = METRICS.get(metric_id)
    if m is None:
        raise KeyError(f"no template for metric {metric_id}; certified templates: {', '.join(sorted(METRICS))}")
    where = list(m.where) + list(extra_where or [])
    if m.date_col and start:
        where.append(f"{m.date_col} >= DATE '{_iso(start)}'")
    if m.date_col and end:
        where.append(f"{m.date_col} < DATE '{_iso(end)}' + INTERVAL 1 DAY")
    select, group = [], ""
    if group_by:
        expr = m.dims.get(group_by)
        if expr is None:
            raise KeyError(f"{metric_id} cannot be grouped by {group_by}; options: {', '.join(sorted(m.dims))}")
        select.append(f"{expr} AS {group_by}")
        group = " GROUP BY 1 ORDER BY 1"
    select += [f"{expr} AS {name}" for name, expr in m.values] + [f"{m.count_expr} AS {m.count_name}"]
    sql = f"SELECT {', '.join(select)} FROM {m.source}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return sql + group


def _iso(d: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise ValueError(f"dates must be YYYY-MM-DD, got {d!r}")
    return d


def roll_rate_sql(start_month_end: str, end_month_end: str, from_bucket=(1, 30), group_by: str = "product_type") -> str:
    """Roll rate (account grain): accounts in the bucket at the start month-end that are worse at the end."""
    lo, hi = from_bucket
    g = {"product_type": "a.product_type", None: None}.get(group_by, "a.product_type")
    sel = f"{g} AS product_type, " if g else ""
    return (
        "WITH s AS (SELECT account_id, product_type, coalesce(try_strptime(month_end_date, '%Y-%m-%d'), "
        "try_strptime(month_end_date, '%d/%m/%Y'), try_strptime(month_end_date, '%Y%m%d'))::DATE AS me, dpd "
        "FROM bronze.account_monthly_snapshot WHERE dpd IS NOT NULL) "
        f"SELECT {sel}round(100.0 * avg(CASE WHEN b.dpd > {hi} THEN 1 ELSE 0 END), 1) AS roll_rate_pct, "
        "count(*) AS accounts FROM s a JOIN s b ON a.account_id = b.account_id "
        f"AND b.me = DATE '{_iso(end_month_end)}' WHERE a.me = DATE '{_iso(start_month_end)}' "
        f"AND a.dpd BETWEEN {lo} AND {hi}" + (" GROUP BY 1 ORDER BY 1" if g else ""))


def catalogue() -> str:
    """Short description of every template, for the LLM prompt."""
    lines = []
    for m in METRICS.values():
        lines.append(f"- {m.metric_id}: values {', '.join(n for n, _ in m.values)}; time basis {m.date_col or 'snapshot'}; "
                     f"group_by one of {', '.join(sorted(m.dims))}" + (f"; {m.note}" if m.note else ""))
    lines.append("- roll_rate: start_month_end, end_month_end (YYYY-MM-DD); group_by product_type")
    return "\n".join(lines)
