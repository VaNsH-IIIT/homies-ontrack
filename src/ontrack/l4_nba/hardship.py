"""Hardship routing: who goes to the human-only queue, and why (owner: P3).

Two separate questions, answered for every open case:

* **hardship_flag**: is the customer in financial hardship? Evidence, any of
    - the case's own ``hardship_flag`` (set by the bank),
    - the customer said so in a note or call in the last 90 days (P2's ``features.text_signals_case``,
      with the verbatim quote as evidence),
    - an income shock, for customers paid by an employer into a deposit account with us: salary deposit
      missing or late in 2 of the last 3 months, or income down 50%+ against the 6 months before. (In the
      training months such cases cured within 30 days 3-10% of the time, against 43-49% for the rest.
      Customers without payroll deposits are not judged on salary gaps: they never have a salary.)
  Hardship cases get ``hardship_referral`` and a person decides.
* **needs_human_review**: hardship, or anything else a machine should not act on alone: vulnerability,
  a dispute (case flag, mentioned in a note/call, or raised on a contact), a complaint, insolvency /
  deceased / third-party holds, or a cease-communication request.

Every routed case stores its reasons (``routing_reason`` = the first, ``routing_reasons`` = all) and a
``routing_category`` used for the queue split in EVALUATION.md.
"""
from __future__ import annotations

import pandas as pd

from ontrack import config

SALARY_GAP_MONTHS = 2          # of the last 3 months
INCOME_DROP_PCT = -0.50        # vs the 6 months before

# (category, is_hardship) in priority order: the first match is the case's routing_category
CATEGORIES = [
    ("hardship_case_flag", True),
    ("hardship_text", True),
    ("hardship_income", True),
    ("vulnerability", False),
    ("dispute", False),
    ("complaint", False),
    ("hold", False),
    ("cease", False),
]


def _truthy(v) -> bool:
    """True only for a real true value; None, NaN and pandas NA are false (bool(pd.NA) would raise)."""
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):   # list-like values: pd.isna returns an array
        pass
    return bool(v)


def _num(v, default=0.0) -> float:
    try:
        return default if v is None or pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return default


def _check_structured(row: dict) -> list[tuple[str, str]]:
    """(category, reason) from the case and customer flags."""
    out = []
    if _truthy(row.get("hardship_flag")):
        why = row.get("hardship_reason")
        out.append(("hardship_case_flag", "Case flagged for hardship"
                    + (f" ({str(why).replace('_', ' ')})" if _truthy(why) else "")))
    if _truthy(row.get("vulnerability_flag")):
        out.append(("vulnerability", "Customer is flagged as vulnerable: needs a certified agent"))
    if _truthy(row.get("dispute_flag")):
        out.append(("dispute", "Open dispute on the case"))
    if _truthy(row.get("complaint_flag")):
        out.append(("complaint", "Open complaint on the case"))
    if _truthy(row.get("insolvency_flag")):
        out.append(("hold", "Insolvency hold (bankruptcy or consumer proposal)"))
    if _truthy(row.get("deceased_flag")):
        out.append(("hold", "Deceased hold"))
    if _truthy(row.get("third_party_hold_flag")):
        out.append(("hold", "Third-party representative on file: contact them, not the customer"))
    if _truthy(row.get("cease_communication_flag")):
        out.append(("cease", "Customer asked us to stop contacting them"))
    return out


def _check_income(row: dict) -> list[tuple[str, str]]:
    """Income shock from salary deposits (point-in-time features), payroll customers only."""
    out = []
    if not _truthy(row.get("has_payroll")):
        return out
    gaps = int(_num(row.get("salary_gap_months_3m")))
    if gaps >= SALARY_GAP_MONTHS:
        out.append(("hardship_income", f"Salary deposit missing or late in {gaps} of the last 3 months"))
    drop = row.get("salary_drop_pct")
    if drop is not None and not pd.isna(drop) and float(drop) <= INCOME_DROP_PCT:
        out.append(("hardship_income", f"Income down {abs(float(drop)):.0%} against the 6 months before"))
    return out


def _check_text(row: dict) -> list[tuple[str, str]]:
    """Signals from notes and calls (P2's features.text_signals_case). Disputes count without hardship."""
    out = []
    if _truthy(row.get("text_hardship_90d")):
        quote = str(row.get("text_hardship_evidence") or "").strip()
        if len(quote) > 140:
            quote = quote[:137].rstrip() + "..."
        out.append(("hardship_text", f'Customer described hardship in the last 90 days: "{quote}"' if quote
                    else "Customer described hardship in a note or call in the last 90 days"))
    if _truthy(row.get("text_dispute_any")):
        out.append(("dispute", "Customer disputed the debt in a note or call"))
    if _truthy(row.get("dispute_raised_any")) and not _truthy(row.get("dispute_flag")):
        out.append(("dispute", "Dispute raised on a past contact"))
    return out


def assess_hardship(row: dict) -> dict:
    """Route one case. Returns hardship_flag, needs_human_review, routing_category, routing_reason(s)."""
    found = _check_structured(row) + _check_text(row) + _check_income(row)
    order = {c: i for i, (c, _) in enumerate(CATEGORIES)}
    found.sort(key=lambda x: order[x[0]])
    hardship_cats = {c for c, h in CATEGORIES if h}
    reasons = list(dict.fromkeys(r for _, r in found))
    return {
        "hardship_flag": any(c in hardship_cats for c, _ in found),
        "needs_human_review": bool(found),
        "routing_category": found[0][0] if found else None,
        "routing_reason": reasons[0] if reasons else None,
        "routing_reasons": "; ".join(reasons) if reasons else None,
    }


ROUTING_SQL = """
SELECT f.case_id,
       coalesce(c.hardship_flag, false) AS hardship_flag, c.hardship_reason,
       coalesce(c.dispute_flag, false) AS dispute_flag,
       coalesce(c.complaint_flag, false) AS complaint_flag,
       coalesce(cu.vulnerability_flag, false) OR coalesce(c.vulnerable_customer_flag, false) AS vulnerability_flag,
       coalesce(cu.insolvency_flag, false) OR coalesce(c.insolvency_hold_flag, false) AS insolvency_flag,
       coalesce(cu.deceased_flag, false) OR coalesce(c.deceased_hold_flag, false) AS deceased_flag,
       coalesce(cu.third_party_hold_flag, false) OR coalesce(c.third_party_rep_flag, false) AS third_party_hold_flag,
       coalesce(cu.cease_communication_flag, false) OR coalesce(c.cease_contact_flag, false) AS cease_communication_flag,
       f.has_payroll, f.salary_gap_months_3m, f.salary_drop_pct, f.dispute_raised_any,
       {text_cols}
FROM features.case_features f
JOIN gold.case_360 c ON c.case_id = f.case_id
LEFT JOIN gold.c360_customer cu ON cu.golden_id = f.golden_id
{text_join}
WHERE f.as_of_date = DATE '{as_of}'
"""

TEXT_COLS = ("t.text_hardship_90d, t.text_hardship_evidence, t.text_hardship_source, "
             "t.text_hardship_confidence, t.text_dispute_any")
NO_TEXT_COLS = ("NULL::BOOLEAN AS text_hardship_90d, NULL::VARCHAR AS text_hardship_evidence, "
                "NULL::VARCHAR AS text_hardship_source, NULL::DOUBLE AS text_hardship_confidence, "
                "NULL::BOOLEAN AS text_dispute_any")


def has_text_signals(con) -> bool:
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'features' "
                            "AND table_name = 'text_signals_case'").fetchone()[0])


def route_cases(con, as_of: str = config.SNAPSHOT_DATE) -> pd.DataFrame:
    """Route every case in features.case_features at ``as_of`` (one query, one join on text signals)."""
    text = has_text_signals(con)
    sql = ROUTING_SQL.format(
        as_of=as_of,
        text_cols=TEXT_COLS if text else NO_TEXT_COLS,
        text_join="LEFT JOIN features.text_signals_case t ON t.case_id = f.case_id" if text else "")
    df = con.execute(sql).fetchdf()
    routed = pd.DataFrame([assess_hardship(r) for r in df.to_dict("records")], index=df.index)
    out = pd.concat([df[["case_id"]], routed], axis=1)
    has_text = df["text_hardship_90d"].astype("boolean").fillna(False).astype(bool)
    out["text_evidence"] = df["text_hardship_evidence"].where(has_text)
    out["text_source"] = df["text_hardship_source"].where(has_text)
    if not text:
        print("  (features.text_signals_case not found: routing without text signals)")
    return out


def print_summary(routed: pd.DataFrame) -> None:
    n = len(routed)
    print(f"Hardship routing: {n:,} open cases")
    print(f"  hardship flagged:   {int(routed['hardship_flag'].sum()):>7,}")
    print(f"  human-only queue:   {int(routed['needs_human_review'].sum()):>7,}  "
          f"({routed['needs_human_review'].mean():.0%})")
    split = routed["routing_category"].value_counts()
    for cat, _ in CATEGORIES:
        if cat in split:
            print(f"    {cat:20s} {int(split[cat]):>7,}")
