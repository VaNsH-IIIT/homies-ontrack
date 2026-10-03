"""Hardship routing: flag cases that must go to a human-only queue (owner: P3).

Combines structured signals (payroll delay, EI deposits, payment failures,
case hardship_flag) with text signals from P2 (when available).
"""
from __future__ import annotations

import datetime as dt


STRUCTURED_SIGNALS = [
    "hardship_flag",
    "vulnerability_flag",
    "dispute_flag",
    "complaint_flag",
]


def _check_structured(case_row: dict) -> list[str]:
    """Return routing reasons from structured case/customer fields."""
    reasons = []
    if case_row.get("hardship_flag"):
        reasons.append("Case flagged for hardship")
    if case_row.get("vulnerability_flag"):
        reasons.append("Customer has vulnerability flag")
    if case_row.get("dispute_flag"):
        reasons.append("Active dispute on case")
    if case_row.get("complaint_flag"):
        reasons.append("Active complaint on case")
    if case_row.get("insolvency_flag"):
        reasons.append("Customer is in insolvency/bankruptcy")
    if case_row.get("deceased_flag"):
        reasons.append("Customer is deceased")
    dpd = case_row.get("dpd_at_entry", 0) or 0
    if dpd == 0 and case_row.get("total_past_due", 0) == 0:
        reasons.append("No delinquency — possible data or hardship case")
    return reasons


def _check_payment_distress(case_row: dict) -> list[str]:
    """Detect payment distress patterns from feature values."""
    reasons = []
    payments_90d = case_row.get("payments_90d", 0) or 0
    payments_30d = case_row.get("payments_30d", 0) or 0
    days_since = case_row.get("days_since_last_payment", 999) or 999
    if payments_90d >= 2 and payments_30d == 0 and days_since > 45:
        reasons.append("Payment pattern suggests sudden financial difficulty (was paying, then stopped)")
    return reasons


def _check_text_signals(con, case_id: str) -> list[str]:
    """Pull text signals from P2's features.text_signals if available."""
    reasons = []
    try:
        rows = con.execute("""
            SELECT hardship_signal, hardship_confidence, evidence_quote,
                   stated_delay_reason, dispute_mentioned
            FROM features.text_signals
            WHERE case_id = ? AND hardship_signal = true
            ORDER BY event_ts DESC LIMIT 3
        """, [case_id]).fetchall()
    except Exception:
        return reasons

    for row in rows:
        conf = row[1] or 0
        quote = row[2] or ""
        if conf >= 0.7:
            snippet = quote[:80] + "..." if len(quote) > 80 else quote
            reasons.append(f"Hardship detected in conversation: \"{snippet}\" (confidence {conf:.0%})")
        delay = row[3]
        if delay:
            reasons.append(f"Customer stated delay reason: {delay}")
        if row[4]:
            reasons.append("Dispute mentioned in conversation")
    return reasons


def assess_hardship(
    case_row: dict,
    con=None,
) -> tuple[bool, bool, list[str]]:
    """Assess hardship and human review need for a case.

    Returns
    -------
    hardship_flag : bool
        True if the case should be treated as hardship.
    needs_human_review : bool
        True if the case must go to a human-only queue.
    reasons : list[str]
        Plain-English reasons for the routing decision.
    """
    reasons = []

    reasons.extend(_check_structured(case_row))
    reasons.extend(_check_payment_distress(case_row))

    if con is not None:
        case_id = case_row.get("case_id")
        if case_id:
            reasons.extend(_check_text_signals(con, str(case_id)))

    hardship = bool(reasons)
    needs_human = hardship
    return hardship, needs_human, reasons


def route_hardship_cases(con, as_of_ts: dt.datetime | None = None) -> int:
    """Flag hardship cases in gold.nba_recommendation and print routing counts."""
    try:
        recs = con.execute("""
            SELECT r.case_id, r.golden_id,
                   cs.hardship_flag, cs.complaint_flag,
                   cu.vulnerability_flag, cu.insolvency_flag, cu.deceased_flag,
                   f.payments_90d, f.payments_30d, f.days_since_last_payment,
                   f.total_past_due, f.dpd_at_entry
            FROM gold.nba_recommendation r
            JOIN gold.case_360 cs ON cs.case_id = r.case_id
            LEFT JOIN gold.c360_customer cu ON cu.golden_id = r.golden_id
            LEFT JOIN features.case_features f ON f.case_id = r.case_id
        """).fetchdf()
    except Exception:
        print("No recommendations to route.")
        return 0

    hardship_count = 0
    human_review_count = 0
    routing_reasons = []

    for _, row in recs.iterrows():
        row_dict = row.to_dict()
        hardship, needs_human, reasons = assess_hardship(row_dict, con)
        if hardship:
            hardship_count += 1
        if needs_human:
            human_review_count += 1
        if reasons:
            routing_reasons.append((row_dict["case_id"], reasons))

        if hardship or needs_human:
            con.execute("""
                UPDATE gold.nba_recommendation
                SET hardship_flag = ?, needs_human_review = ?
                WHERE case_id = ?
            """, [hardship, needs_human, str(row_dict["case_id"])])

    print(f"\nHardship routing summary:")
    print(f"  Total cases:        {len(recs):,d}")
    print(f"  Hardship flagged:   {hardship_count:,d}")
    print(f"  Human review queue: {human_review_count:,d}")

    if routing_reasons:
        print(f"\nSample routing reasons (first 5):")
        for case_id, reasons in routing_reasons[:5]:
            print(f"  Case {case_id}:")
            for r in reasons[:3]:
                print(f"    - {r}")

    return hardship_count
