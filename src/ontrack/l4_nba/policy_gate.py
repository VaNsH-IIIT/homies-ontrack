"""Policy gate: hard constraints that block actions before any model runs (owner: P3).

For each open case the gate returns the set of allowed actions and the set of
blocked actions, each with a plain-English rule reason.  Rules fire first; no
model can override a blocked action.

The gate is re-checked at send time in production, but for the hackathon v0 we
check at scoring time only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ontrack import config

ACTIONS = (
    "do_nothing",
    "call",
    "sms",
    "email",
    "push_notification",
    "reminder_letter",
    "hardship_referral",
    "specialist_agent",
)

CHANNEL_ACTIONS = {
    "call": "call",
    "sms": "sms",
    "email": "email",
    "push_notification": "push",
}

CONSENT_MAP = {
    "call": "consent_call",
    "sms": "consent_sms",
    "email": "consent_email",
    "push_notification": "consent_push",
}

OUTBOUND_ACTIONS = {"call", "sms", "email", "push_notification", "reminder_letter"}

CANADA_STAT_HOLIDAYS_2026 = {
    dt.date(2026, 1, 1),    # New Year's Day
    dt.date(2026, 2, 16),   # Family Day (Ontario)
    dt.date(2026, 4, 3),    # Good Friday
    dt.date(2026, 5, 18),   # Victoria Day
    dt.date(2026, 7, 1),    # Canada Day
    dt.date(2026, 8, 3),    # Civic Holiday
    dt.date(2026, 9, 7),    # Labour Day
    dt.date(2026, 9, 30),   # National Day for Truth and Reconciliation
    dt.date(2026, 10, 12),  # Thanksgiving
    dt.date(2026, 11, 11),  # Remembrance Day
    dt.date(2026, 12, 25),  # Christmas
    dt.date(2026, 12, 26),  # Boxing Day
}


@dataclass
class ActionResult:
    action: str
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _get(row: dict[str, Any], key: str, default: Any = None) -> Any:
    v = row.get(key, default)
    if v is None:
        return default
    return v


def check_consent(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Block channel actions where the customer has not given consent."""
    blocks = []
    for action, consent_col in CONSENT_MAP.items():
        if not _get(row, consent_col, False):
            blocks.append((action, f"No {consent_col.replace('_', ' ')} from customer"))
    # consent_autodialer only governs automated dialling: an agent's manual call needs consent_call alone.
    # The note is added by service_notes() so the agent dials manually.
    return blocks


def check_cease_communication(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Cease communication flag blocks all outbound contact."""
    if _get(row, "cease_communication_flag", False):
        return [(a, "Cease communication flag is active") for a in OUTBOUND_ACTIONS]
    return []


def check_do_not_call(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Internal do-not-call flag blocks phone calls."""
    blocks = []
    if _get(row, "internal_do_not_call_flag", False):
        blocks.append(("call", "Internal do-not-call flag is active"))
    if _get(row, "national_dncl_flag", False):
        blocks.append(("call", "Customer is on the national do-not-call list"))
    return blocks


def check_holds(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Insolvency, deceased, and third-party holds block automated actions."""
    blocks = []
    if _get(row, "insolvency_flag", False):
        for a in OUTBOUND_ACTIONS:
            blocks.append((a, "Insolvency hold — account is in bankruptcy or consumer proposal"))
    if _get(row, "deceased_flag", False):
        for a in ACTIONS:
            if a != "do_nothing":
                blocks.append((a, "Deceased flag is active — no contact permitted"))
    if _get(row, "third_party_hold_flag", False):
        blocks.append(("call", "Third-party hold — must contact representative, not customer directly"))
        blocks.append(("sms", "Third-party hold — direct customer contact blocked"))
        blocks.append(("push_notification", "Third-party hold — direct customer contact blocked"))
    return blocks


def check_dispute(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Open dispute blocks escalation actions."""
    blocks = []
    if _get(row, "dispute_flag", False) or _get(row, "credit_counselling_agency_flag", False):
        for a in OUTBOUND_ACTIONS:
            blocks.append((a, "Open dispute or credit counselling agency involved"))
    return blocks


def check_contact_cap(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Block actions if the 7-day contact cap has been reached."""
    blocks = []
    contacts_7d = _get(row, "contacts_last_7d", 0)
    cap_7d = _get(row, "contact_cap_7d", 7)
    if contacts_7d >= cap_7d:
        for a in OUTBOUND_ACTIONS:
            blocks.append((a, f"Contact cap reached ({contacts_7d}/{cap_7d} contacts in last 7 days)"))
    return blocks


def check_permitted_hours(row: dict[str, Any], as_of_ts: dt.datetime | None = None) -> list[tuple[str, str]]:
    """Block calls outside permitted calling hours."""
    blocks = []
    if as_of_ts is None:
        return blocks

    start_str = _get(row, "permitted_call_start_local")
    end_str = _get(row, "permitted_call_end_local")
    if start_str is None or end_str is None:
        return blocks

    try:
        start_hour = int(str(start_str).split(":")[0])
        end_hour = int(str(end_str).split(":")[0])
    except (ValueError, IndexError):
        return blocks

    local_hour = as_of_ts.hour
    if local_hour < start_hour or local_hour >= end_hour:
        blocks.append(("call", f"Outside permitted calling hours ({start_str}–{end_str} local)"))
    return blocks


def check_stat_holidays(row: dict[str, Any], as_of_ts: dt.datetime | None = None) -> list[tuple[str, str]]:
    """Block calls on statutory holidays and Sundays if not permitted."""
    blocks = []
    if as_of_ts is None:
        return blocks

    as_of_date = as_of_ts.date() if isinstance(as_of_ts, dt.datetime) else as_of_ts
    if as_of_date in CANADA_STAT_HOLIDAYS_2026:
        blocks.append(("call", f"Statutory holiday ({as_of_date.isoformat()}) — no outbound calls"))

    if as_of_date.weekday() == 6 and not _get(row, "sunday_contact_permitted", False):
        blocks.append(("call", "Sunday contact not permitted for this customer"))
    return blocks


def check_hardship(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Flag hardship cases for human-only routing."""
    blocks = []
    if _get(row, "hardship_flag", False) or _get(row, "vulnerability_flag", False):
        blocks.append(("call", "Hardship/vulnerability flagged — must route to specialist"))
        blocks.append(("sms", "Hardship/vulnerability flagged — must route to specialist"))
    return blocks


def service_notes(row: dict[str, Any]) -> list[str]:
    """How to serve the customer, without blocking anything.

    Language of service routes the call to an agent who speaks it; blocking calls for French-speaking
    customers (as v0 did) would treat them differently from everyone else.
    """
    notes = []
    lang = str(_get(row, "preferred_language", "EN") or "EN").upper()
    if lang.startswith("FR"):
        notes.append("Serve in French: route to a French-speaking agent")
    if not _get(row, "consent_autodialer", False):
        notes.append("No autodialer consent: agent dials manually")
    return notes


ALL_RULES = [
    check_consent,
    check_cease_communication,
    check_do_not_call,
    check_holds,
    check_dispute,
    check_contact_cap,
    check_permitted_hours,
    check_stat_holidays,
    check_hardship,
]

RULES_NEEDING_TIMESTAMP = {check_permitted_hours, check_stat_holidays}


def evaluate(row: dict[str, Any], as_of_ts: dt.datetime | None = None) -> dict[str, ActionResult]:
    """Run every policy rule and return the per-action result.

    Parameters
    ----------
    row : dict
        Merged customer + case row with all relevant columns.
    as_of_ts : datetime, optional
        The timestamp to check time-dependent rules (permitted hours, holidays).
        If None, time-dependent rules are skipped.

    Returns
    -------
    dict mapping action name -> ActionResult
    """
    results: dict[str, ActionResult] = {
        a: ActionResult(action=a, allowed=True) for a in ACTIONS
    }

    for rule_fn in ALL_RULES:
        if rule_fn in RULES_NEEDING_TIMESTAMP:
            blocks = rule_fn(row, as_of_ts)
        else:
            blocks = rule_fn(row)

        for action, reason in blocks:
            if action in results:
                results[action].allowed = False
                if reason not in results[action].reasons:
                    results[action].reasons.append(reason)

    # do_nothing is always allowed (self-cure path)
    results["do_nothing"].allowed = True
    results["do_nothing"].reasons = []

    return results


def get_allowed_actions(row: dict[str, Any], as_of_ts: dt.datetime | None = None) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Convenience: return (allowed, blocked, blocked_reasons).

    Returns
    -------
    allowed : list[str]
        Actions the agent may take.
    blocked : list[str]
        Actions that are blocked.
    blocked_reasons : dict[str, list[str]]
        Mapping from blocked action to list of rule reasons.
    """
    results = evaluate(row, as_of_ts)
    allowed = [a for a, r in results.items() if r.allowed]
    blocked = [a for a, r in results.items() if not r.allowed]
    blocked_reasons = {a: r.reasons for a, r in results.items() if not r.allowed}
    return allowed, blocked, blocked_reasons


HUMAN_REVIEW_RULES = (
    ("hardship_flag", "Hardship flagged — requires human review before any action"),
    ("vulnerability_flag", "Vulnerability flagged — requires human review"),
    ("dispute_flag", "Open dispute — requires human review"),
    ("complaint_flag", "Complaint case — requires human review"),
    ("insolvency_flag", "Insolvency hold — requires human review"),
    ("deceased_flag", "Deceased hold — requires human review"),
    ("third_party_hold_flag", "Third-party representative — requires human review"),
    ("cease_communication_flag", "Customer asked us to stop contacting them — requires human review"),
)


def needs_human_review(row: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if this case must go to the human-only queue (first matching rule gives the reason)."""
    for col, reason in HUMAN_REVIEW_RULES:
        if _get(row, col, False):
            return True, reason
    return False, None


def build_gate_for_cases(con, as_of_ts: dt.datetime | None = None) -> None:
    """Run the policy gate on all open cases and print a summary.

    Reads from gold.c360_customer, gold.case_360, and gold.contact_timeline,
    and prints how many actions are allowed vs blocked across all open cases.
    """
    cases_df = con.execute("""
        SELECT
            cs.case_id,
            cs.golden_id,
            cu.consent_call,
            cu.consent_sms,
            cu.consent_email,
            cu.consent_push,
            cu.consent_autodialer,
            cu.internal_do_not_call_flag,
            cu.cease_communication_flag,
            cu.insolvency_flag,
            cu.deceased_flag,
            cu.third_party_hold_flag,
            cu.vulnerability_flag,
            cu.preferred_language,
            cu.province_code,
            cu.time_zone,
            cs.hardship_flag,
            cs.complaint_flag,
            (SELECT count(*) FROM gold.contact_timeline ct
             WHERE ct.case_id = cs.case_id
             AND ct.contact_ts_utc >= DATE '{snap}' - INTERVAL '7 days') AS contacts_last_7d
        FROM gold.case_360 cs
        LEFT JOIN gold.c360_customer cu ON cu.golden_id = cs.golden_id
        WHERE cs.outcome IS NULL
    """.replace("{snap}", config.SNAPSHOT_DATE)).fetchdf()

    total_allowed = 0
    total_blocked = 0
    for _, row in cases_df.iterrows():
        allowed, blocked, _ = get_allowed_actions(row.to_dict(), as_of_ts)
        total_allowed += len(allowed)
        total_blocked += len(blocked)

    n = len(cases_df)
    print(f"Policy gate: {n:,d} open cases")
    print(f"  Average allowed actions: {total_allowed / max(n, 1):.1f} / {len(ACTIONS)}")
    print(f"  Average blocked actions: {total_blocked / max(n, 1):.1f} / {len(ACTIONS)}")
