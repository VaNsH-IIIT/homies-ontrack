"""'Understood as' tokens: question -> metric, window, grouping, filters (owner: P2).

Design, Layer 2 step 2: the user sees (and can edit) how the question was understood. Relative dates resolve
against the snapshot (28 Sep 2026), never the wall clock. These tokens drive the certified-metric templates, so a
certified question needs no LLM and always gives the same number.
"""
from __future__ import annotations

import calendar
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from ontrack import config
from ontrack.l2_ask import metrics

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9

# phrase after "by" -> group-by token (first match wins, so longer phrases first)
GROUP_ALIASES = [
    (r"number of previously broken promises|previously broken|prior broken", "prior_broken"),
    (r"agent site|site", "site"),
    (r"local hour of day|hour of day|hour", "contact_hour_local"),
    (r"card product|product code", "product_code"),
    (r"primary product", "primary_product"),
    (r"current bucket|dpd bucket|bucket", "current_bucket"),
    (r"test cell|strategy cell|champion|challenger", "test_cell"),
    (r"queue", "queue"),
    (r"province", "province_code"),
    (r"channel", "channel"),
    (r"team", "assigned_team"),
    (r"product", "product"),
    (r"month", "month"),
    (r"day of week|weekday", "day_of_week"),
    (r"day|date", "day"),
]

# question words -> certified metric (used when the question file gives no metric_id)
METRIC_ALIASES = [
    (r"broken[- ]promise rate|broken ptp|ptp break", "broken_promise_rate"),
    (r"promise[- ]kept rate|ptp kept|kept promises|promises kept", "promise_kept_rate"),
    (r"right[- ]party contact rate|rpc rate|contact rate|reach rate", "rpc_rate"),
    (r"ptp rate|promise rate", "ptp_rate"),
    (r"cost per right[- ]party|cost per rpc", "cost_per_rpc"),
    (r"cost per contact|contact cost|cost per attempt", "cost_per_contact"),
    (r"hardship rate|hardship share", "hardship_rate"),
    (r"average days past due|average dpd|mean dpd|avg dpd", "average_dpd"),
    (r"delinquency rate|arrears rate|days past due today", "delinquency_rate"),
    (r"attempts per case|contact attempts .* on average|touches per case", "contact_attempts_per_case"),
    (r"cure rate|cured within", "cure_rate"),
    (r"roll(?:ed)? (?:rate|forward|to a worse bucket)|flow rate", "roll_rate"),
    (r"paid against promises|amount collected|how much .* collect", "collected_amount"),
    (r"payroll .* late|payroll delay", "payroll_delay_share"),
    (r"how many (?:collections )?cases are open|number of open cases|open cases? count", "open_case_count"),
]


@dataclass
class Understood:
    metric: str | None = None
    start: str | None = None          # ISO date, inclusive
    end: str | None = None            # ISO date, inclusive
    group_by: str | None = None
    filters: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)   # parts of the question the parser could not map

    def tokens(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], "")}

    def to_json(self) -> str:
        return json.dumps(self.tokens(), ensure_ascii=False)


def _month_range(y: int, m: int) -> tuple[str, str]:
    return date(y, m, 1).isoformat(), date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def parse_window(q: str, snapshot: date) -> tuple[str | None, str | None]:
    ql = q.lower()
    mon = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|" \
          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    # "July-September 2026" / "July to September 2026"
    m = re.search(mon + r"\s*(?:-|–|to)\s*" + mon + r"\s+(\d{4})", ql)
    if m:
        y = int(m.group(3))
        s, _ = _month_range(y, MONTHS[m.group(1)[:3] if m.group(1)[:3] in MONTHS else m.group(1)])
        _, e = _month_range(y, MONTHS[m.group(2)[:3] if m.group(2)[:3] in MONTHS else m.group(2)])
        return s, min(e, snapshot.isoformat())
    # "between 15 and 22 September 2026"
    m = re.search(r"between (\d{1,2}) and (\d{1,2}) " + mon + r" (\d{4})", ql)
    if m:
        mm, y = MONTHS[m.group(3)[:3]], int(m.group(4))
        return date(y, mm, int(m.group(1))).isoformat(), date(y, mm, int(m.group(2))).isoformat()
    # "12 months to 28 September 2026"
    m = re.search(r"(\d+) months to (\d{1,2}) " + mon + r" (\d{4})", ql)
    if m:
        end = date(int(m.group(4)), MONTHS[m.group(3)[:3]], int(m.group(2)))
        n = int(m.group(1))
        start = date(end.year - (n // 12), end.month, end.day) + timedelta(days=1) if n % 12 == 0 else None
        return (start.isoformat() if start else None), end.isoformat()
    # "in September 2026" / "due in August 2026" / "opened in July 2026"
    m = re.search(mon + r" (\d{4})", ql)
    if m:
        return _month_range(int(m.group(2)), MONTHS[m.group(1)[:3]])
    if re.search(r"\blast month\b", ql):
        first = snapshot.replace(day=1) - timedelta(days=1)
        return _month_range(first.year, first.month)
    if re.search(r"\bthis month\b", ql):
        return snapshot.replace(day=1).isoformat(), snapshot.isoformat()
    # "opened in 2026" / "in 2026"
    m = re.search(r"\bin (\d{4})\b", ql)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1).isoformat(), min(date(y, 12, 31), snapshot).isoformat()
    return None, None


def parse_group(q: str, allowed: set[str]) -> tuple[str | None, str | None]:
    """(group_by token, unparsed phrase). Only phrases after 'by' / 'per' / 'compare' count as grouping."""
    ql = q.lower()
    m = re.search(r"\b(?:by|per|for each|change with(?: the)?|compare)\b(.*)$", ql)
    if not m:
        return None, None
    phrase = m.group(1)
    for pattern, token in GROUP_ALIASES:
        if re.search(r"\b(?:" + pattern + r")\b", phrase):
            if token in allowed:
                return token, None
            if token == "product" and "product_code" in allowed:
                return "product_code", None
            if token == "site" and "agent_site" in allowed:
                return "agent_site", None
    return None, phrase.strip(" ?.")


def understand(question: str, metric_id: str | None = None, as_of_date: str = config.SNAPSHOT_DATE) -> Understood:
    snapshot = date.fromisoformat(as_of_date)
    ql = question.lower()
    u = Understood(metric=metric_id or None)
    if not u.metric:
        for pattern, mid in METRIC_ALIASES:
            if re.search(pattern, ql):
                u.metric = mid
                break
    if not u.metric:
        return u
    u.start, u.end = parse_window(question, snapshot)
    if u.metric == "roll_rate":
        return u
    m = metrics.METRICS.get(u.metric)
    if m is None:
        u.unresolved.append(f"no template for {u.metric}")
        return u
    u.group_by, rest = parse_group(question, set(m.dims))
    if rest:
        u.unresolved.append(f"grouping '{rest}'")
    if re.search(r"\brandomi[sz]ed\b", ql):
        u.filters.append("c.assignment_method = 'random'" if "c." in m.source or u.metric.startswith(("promise", "broken"))
                         else "assignment_method = 'random'")
        if u.group_by == "test_cell":
            cells = re.findall(r"\b(champion|challenger_[a-z])\b", question, re.I)
            if cells:
                u.filters.append("c.test_cell IN (" + ", ".join(f"'{c}'" for c in cells) + ")")
    if u.metric in ("contact_attempts_per_case",) and re.search(r"\bopen cases?\b", ql):
        u.filters.append("c.outcome IS NULL")
    if u.metric == "cure_rate" and not re.search(r"within 30 days", ql):
        u.unresolved.append("cure window (template is 30 days from opening)")
    if m.date_col is None and (u.start or u.end) and not re.search(r"\btoday\b", ql):
        u.unresolved.append("time window on a snapshot metric")
    return u


def to_sql(u: Understood) -> str:
    if u.metric == "roll_rate":
        raise ValueError("roll rate needs start and end month-ends; use metrics.roll_rate_sql")
    return metrics.certified_sql(u.metric, u.start, u.end, u.group_by, u.filters)
