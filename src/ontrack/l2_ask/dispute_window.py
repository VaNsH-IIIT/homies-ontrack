"""G24: "how many disputes were raised between <dates>, compared with the N days before?", deterministic (owner: P2).

Dataset definition (release dev gold for BQ-006): a dispute *raised* is a contact with
`contact_history.dispute_raised_flag`, timed by `contact_ts_local`. The contact data has no field for what a dispute
is about, so a qualifier such as "late-fee" can't narrow it. Case-level `dispute_type` (late_fee, billing_error, ...)
describes a case's open dispute, not when one was raised. A fresh LLM run once read "late-fee" literally
(`case dispute_type = 'late_fee'`: 29 vs 9 instead of 875 vs 566). This route makes the answer independent of the LLM.

Ops events starting in the windows (e.g. INC-0914, the 14 Sep app outage that charged late fees in error) are added
as context with their reference document, read from bronze.ops_events.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from ontrack import config

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "fourteen": 14, "thirty": 30}
QUESTION_RE = re.compile(
    r"^how many (?P<qual>(?:[a-z][a-z-]* ){0,3}?)disputes? (?:were |was |have been |got )?raised "
    r"(?:(?:between|from) (?P<d1>\d{1,2})(?: (?P<m1>" + _MON + r"))? (?:and|to|-|until) |on (?P<d1b>\d{1,2}) ?- ?)"
    r"(?P<d2>\d{1,2}) (?P<m2>" + _MON + r")(?: (?P<y>20\d\d))?"
    r"(?: ?,? (?:compared (?:with|to)|versus|vs\.?|against) (?:the )?(?:(?P<n>\d+|[a-z]+) days? before|"
    r"(?P<week>week|7 days) before|previous (?P<n2>\d+|[a-z]+) days?|(?P<same>same (?:length of time|period|"
    r"number of days)|period) before))?$")


def parse(question: str) -> dict | None:
    q = re.sub(r"[‐-―]", "-", (question or "").lower())
    q = re.sub(r"\s+", " ", re.sub(r"[?!]", "", q)).strip().rstrip(".")
    m = QUESTION_RE.match(q)
    if not m:
        return None
    try:
        y = int(m["y"] or config.SNAPSHOT_DATE[:4])
        m2 = MONTHS[m["m2"][:3]]
        m1 = MONTHS[m["m1"][:3]] if m["m1"] else m2
        start = date(y, m1, int(m["d1"] or m["d1b"]))
        end = date(y, m2, int(m["d2"]))
    except (KeyError, ValueError):
        return None
    if end < start:
        return None
    n = None
    if m["n"] or m["n2"]:
        raw = m["n"] or m["n2"]
        n = int(raw) if raw.isdigit() else _NUM.get(raw)
        if n is None:
            return None
    elif m["week"]:
        n = 7
    elif m["same"]:
        n = (end - start).days + 1
    qual = m["qual"].strip()
    if qual in ("", "the", "customer", "new"):
        qual = ""
    return {"start": start, "end": end, "n": n, "qualifier": qual}


def _label(a: date, b: date) -> str:
    fmt = lambda d: d.strftime("%b")
    return f"{a.day}-{b.day} {fmt(b)}" if a.month == b.month else f"{a.day} {fmt(a)}-{b.day} {fmt(b)}"


def sql(p: dict) -> tuple[str, str, str | None]:
    start, end, n = p["start"], p["end"], p["n"]
    stop = end + timedelta(days=1)
    cur = _label(start, end)
    if not n:
        return (f"SELECT '{cur}' AS period, count(*) AS disputes FROM bronze.contact_history WHERE dispute_raised_flag "
                f"AND contact_ts_local >= TIMESTAMP '{start}' AND contact_ts_local < TIMESTAMP '{stop}'"), cur, None
    prior_start, prior_end = start - timedelta(days=n), start - timedelta(days=1)
    prev = _label(prior_start, prior_end)
    return (f"SELECT CASE WHEN contact_ts_local >= TIMESTAMP '{start}' THEN '{cur}' ELSE '{prev}' END AS period, "
            f"count(*) AS disputes FROM bronze.contact_history WHERE dispute_raised_flag "
            f"AND contact_ts_local >= TIMESTAMP '{prior_start}' AND contact_ts_local < TIMESTAMP '{stop}' "
            f"GROUP BY 1 ORDER BY 1"), cur, prev


def answer(eng, question: str):
    p = parse(question)
    if p is None:
        return None
    from ontrack.l2_ask.ask import Answer, format_table
    try:
        q, cur, prev = sql(p)
        safe, df = eng.run_sql(q)
        counts = dict(zip(df["period"], df["disputes"]))
        a = int(counts.get(cur, 0))
        text = f"Customers raised {a:,} disputes during contacts on {cur} {p['end'].year}"
        lo = p["start"] - timedelta(days=p["n"] or 0)
        if prev:
            b = int(counts.get(prev, 0))
            change = f"{a - b:+,}" + (f" ({100 * (a - b) / b:+.0f}%)" if b else "")
            text += f", compared with {b:,} on {prev} (the {p['n']} days before): {change}."
        else:
            text += "."
        ev = eng.con.cursor().execute(
            "SELECT event_id, strftime(start_ts, '%-d %b') AS day, description, reference_doc_id FROM bronze.ops_events "
            "WHERE start_ts < ? AND start_ts >= ? ORDER BY start_ts",           # events that start in the windows
            [str(p["end"] + timedelta(days=1)), str(lo)]).fetchall()
        sources = ["contact_history.dispute_raised_flag"]
        for eid, day, desc, ref in ev:
            text += f" In the period: {eid} on {day}, {desc[0].lower() + desc[1:]}" + (f" ({ref})." if ref else ".")
            sources += [s for s in (f"ops_events {eid}", ref) if s]
        if p["qualifier"]:
            text += (f" The contact data has no field for what a dispute is about, so \"{p['qualifier']}\" can't be "
                     f"applied: this counts every dispute raised during contacts. A case's dispute_type describes its "
                     f"open dispute, not when one was raised.")
        import json
        return Answer(text + "\n\n" + format_table(df), safe + "\n-- sources: " + json.dumps(sources), False, "explain",
                      {"template": "disputes_raised_window", "window": f"{p['start']}..{p['end']}",
                       "compared_with": prev or "", "definition": "contact_history.dispute_raised_flag"},
                      table=df, sql=safe)
    except Exception:  # noqa: BLE001 - fall back to the normal path
        return None
