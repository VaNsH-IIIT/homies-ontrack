"""G20: live "explain" answers in Ask, deterministic, no LLM (owner: P2).

Two question shapes judges ask live, answered from gold in well under a second with the SQL shown:
  * "Why was case CS-2026-583749 given a hardship referral?" / "Explain the recommendation for case <id>"
      -> the case's action, channel and window, its 3 reasons, blocked actions with why, the verified evidence quote
         and why a person reviews it, from gold.nba_recommendation (P3's agent card) + gold.case_360;
  * "Tell me about customer <golden_id | CRM id | any source key>"
      -> the C360 summary: systems linked, products, exposure, overdue, contact consents and protective flags, and
         each open case with its next best action. No names, contact details or protected attributes (the C360
         tables hold none; free text is redacted).
`match()` is pure regex (tested without data). Engine.answer calls `answer()` right after the scope guard, so a
question asking for a case's phone number or name is still refused first.
"""
from __future__ import annotations

import re

CASE_ID_RE = re.compile(r"\bCS-\d{4}-\d{6}\b", re.I)
# The case question must be about the recommendation, not e.g. "summarise the call on case X" (transcript route).
CASE_INTENT_RE = re.compile(r"\b(explain\w*|recommend\w*|next[- ]best[- ]action|nba|blocked|routed|referr\w*|"
                            r"human review|sent to a person|agent card|decision)\b", re.I)
CASE_EXCLUDE_RE = re.compile(r"\b(summari[sz]e|transcript|recorded call|call recording|notes?)\b", re.I)
# "customer VIB-8709", "customer id G-B8B4…", "customer #0055965411": the id must contain a digit.
CUSTOMER_ID_RE = re.compile(r"\bcustomer(?:\s+(?:id|key|number|no\.?|ref))?\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,})",
                            re.I)
CUSTOMER_INTENT_RE = re.compile(r"\b(tell me about|about|summar\w*|profile|overview|describe|look ?up|details?|"
                                r"360|who is|what do (?:we|you) know|show)\b", re.I)
# Personal details are never part of the summary; such questions stay with the scope guard (defence in depth).
PII_RE = re.compile(r"\b(name|address|phone|e-?mail|sin|social insurance|birth|dob|age|gender|marital|"
                    r"citizenship|ethnic\w*|religio\w*)\b", re.I)


def match(question: str) -> tuple[str, str] | None:
    """("case", case_id) or ("customer", key) when the question is one of the two shapes, else None."""
    q = question or ""
    cases = {c.upper() for c in CASE_ID_RE.findall(q)}
    if len(cases) == 1 and CASE_INTENT_RE.search(q) and not CASE_EXCLUDE_RE.search(q):
        return "case", cases.pop()
    if not cases and CUSTOMER_INTENT_RE.search(q) and not PII_RE.search(q):
        ids = [i for i in CUSTOMER_ID_RE.findall(q) if re.search(r"\d", i)]
        if len(ids) == 1:
            return "customer", ids[0].rstrip("-")
    return None


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def case_sql(case_id: str) -> str:
    return ("SELECT r.case_id, r.action, r.channel, r.time_window, r.reason_1, r.reason_2, r.reason_3, "
            "r.blocked_actions, r.blocked_reasons, r.needs_human_review, r.routing_reason, r.text_evidence, "
            "r.text_source, r.counterfactual, r.current_bucket, c.current_dpd, round(c.total_overdue, 2) AS "
            "overdue_cad, c.queue, r.model_version FROM gold.nba_recommendation r JOIN gold.case_360 c "
            f"ON c.case_id = r.case_id WHERE r.case_id = {_lit(case_id)}")


def customer_sql(golden_id: str) -> str:
    return ("SELECT c.golden_id, c.primary_crm_customer_id, c._source_systems AS source_systems, c.source_key_count, "
            "c.match_confidence_min, c.products_held, round(c.total_exposure, 2) AS total_exposure, "
            "round(c.total_overdue, 2) AS total_overdue, c.max_dpd, c.open_case_count, c.case_count, "
            "c.province_code, c.preferred_language, c.consent_call, c.consent_sms, c.consent_email, c.consent_push, "
            "c.internal_do_not_call_flag, c.cease_communication_flag, c.insolvency_flag, c.deceased_flag, "
            f"c.third_party_hold_flag, c.vulnerability_flag FROM gold.c360_customer c WHERE c.golden_id = "
            f"{_lit(golden_id)}")


def open_cases_sql(golden_id: str) -> str:
    return ("SELECT c.case_id, c.primary_product, c.current_dpd, round(c.total_overdue, 2) AS overdue_cad, c.queue, "
            "r.action, r.channel, r.time_window, r.needs_human_review, r.reason_1 FROM gold.case_360 c LEFT JOIN "
            f"gold.nba_recommendation r ON r.case_id = c.case_id WHERE c.golden_id = {_lit(golden_id)} "
            "AND c.outcome IS NULL ORDER BY c.total_overdue DESC, c.case_id LIMIT 50")


def resolve_sql(key: str) -> str:
    return ("SELECT DISTINCT golden_id, source_system FROM gold.customer_xref WHERE upper(source_key) = "
            f"{_lit(key.upper())} OR upper(golden_id) = {_lit(key.upper())} ORDER BY 1, 2 LIMIT 20")


def _money(x) -> str:
    return "" if x is None or x != x else f"${x:,.2f}".replace(".00", "")


def _systems(v) -> list[str]:
    """c360_customer._source_systems is a list (or its text form): system names only."""
    if isinstance(v, str):
        return re.findall(r"[a-z_]+", v)
    return [str(x) for x in (v if v is not None else [])]


def _n(k, word: str) -> str:
    return f"{k} {word}" + ("" if k == 1 else "s")


def _yes(x) -> bool:
    return bool(x) and x == x


def explain_case(eng, case_id: str):
    from ontrack.l2_ask.ask import Answer, format_table, redact
    safe, df = eng.run_sql(case_sql(case_id))
    src = safe + "\n-- sources: [\"gold.nba_recommendation (P3 agent card)\", \"gold.case_360\"]"
    if not len(df):
        return Answer(f"Case {case_id} has no recommendation: it is not an open case on the snapshot "
                      f"(OnTrack scores open cases only).", src, False, "explain", {"case_id": case_id},
                      table=df, sql=safe)
    r = df.iloc[0]
    reasons = [redact(str(x)) for x in (r.reason_1, r.reason_2, r.reason_3) if isinstance(x, str) and x]
    parts = [f"Case {case_id}: recommended action **{r.action}** via {r.channel}, {r.time_window} "
             f"(DPD {r.current_dpd}, {_money(r.overdue_cad)} overdue, queue {r.queue})."]
    parts.append("Why: " + " · ".join(f"{i}) {t}" for i, t in enumerate(reasons, 1)) + ".")
    if isinstance(r.blocked_actions, str) and r.blocked_actions:
        why = r.blocked_reasons if isinstance(r.blocked_reasons, str) and r.blocked_reasons else ""
        parts.append(f"Blocked: {r.blocked_actions}" + (f" ({why})." if why else "."))
    if isinstance(r.text_evidence, str) and r.text_evidence:
        parts.append(f"Evidence: \"{redact(r.text_evidence)}\" ({r.text_source}).")
    if _yes(r.needs_human_review):
        parts.append("A person reviews it first" + (f": {r.routing_reason}." if isinstance(r.routing_reason, str)
                                                    and r.routing_reason else "."))
    if isinstance(r.counterfactual, str) and r.counterfactual:
        parts.append(f"What would change it: {r.counterfactual}.")
    text = " ".join(p.replace("..", ".") for p in parts)
    return Answer(text + "\n\n" + format_table(df[["case_id", "action", "reason_1", "blocked_actions",
                                                    "text_evidence"]]),
                  src, False, "explain", {"case_id": case_id, "source": "gold.nba_recommendation"},
                  table=df.T.reset_index().rename(columns={"index": "field", 0: "value"}).astype(str), sql=safe)


def explain_customer(eng, key: str):
    from ontrack.l2_ask.ask import Answer, format_table
    rsql, ids = eng.run_sql(resolve_sql(key))
    gids = sorted(set(ids["golden_id"])) if len(ids) else []
    if len(gids) != 1:
        msg = (f"No customer with key {key} in the customer 360 (golden id, CRM id or any source system key)."
               if not gids else f"Key {key} links to {len(gids)} golden customers: {', '.join(gids)}. "
                                f"Ask about one golden id.")
        return Answer(msg, rsql, False, "explain", {"customer_key": key}, table=ids, sql=rsql)
    gid = gids[0]
    key_system = " / ".join(sorted(set(ids["source_system"])))
    ssql, s = eng.run_sql(customer_sql(gid))
    osql, o = eng.run_sql(open_cases_sql(gid))
    sql = ";\n\n".join([rsql, ssql, osql])
    src = sql + "\n-- sources: [\"gold.customer_xref\", \"gold.c360_customer\", \"gold.case_360\", " \
                "\"gold.nba_recommendation\"]"
    c = s.iloc[0]
    systems = ", ".join(sorted(set(_systems(c.source_systems))))
    who = (f"Customer {key} (a {key_system} key) is golden customer" if key.upper() != gid.upper()
           else "Golden customer")
    consents = [ch for ch in ("call", "sms", "email", "push") if _yes(c[f"consent_{ch}"])]
    flags = [f.replace("_flag", "").replace("_", " ") for f in ("vulnerability_flag", "insolvency_flag",
             "deceased_flag", "cease_communication_flag", "internal_do_not_call_flag", "third_party_hold_flag")
             if _yes(c[f])]
    parts = [f"{who} **{gid}**: {_n(c.source_key_count, 'source key')} linked across {systems} (lowest match "
             f"confidence {c.match_confidence_min:.2f}).",
             f"{_n(c.products_held, 'product')}, total exposure {_money(c.total_exposure)}, overdue "
             f"{_money(c.total_overdue)}, max DPD {c.max_dpd}; {_n(c.open_case_count, 'open case')} "
             f"({c.case_count} in total).",
             f"Province {c.province_code}, language {c.preferred_language}; consents: "
             f"{', '.join(consents) or 'none'}; protective flags: {', '.join(flags) or 'none'}."]
    for _, r in o.iterrows():
        parts.append(f"Open case {r.case_id} ({r.primary_product}, DPD {r.current_dpd}, {_money(r.overdue_cad)} "
                     f"overdue): next best action **{r.action}** via {r.channel}, {r.time_window}"
                     + (" (a person reviews it first)" if _yes(r.needs_human_review) else "")
                     + (f"; {r.reason_1}" if isinstance(r.reason_1, str) else "") + ".")
    text = " ".join(parts)
    summary = s[["golden_id", "products_held", "total_exposure", "open_case_count"]]
    return Answer(text + "\n\n" + format_table(summary) + ("\n\n" + format_table(o) if len(o) else ""),
                  src, False, "explain", {"customer_key": key, "golden_id": gid}, table=o if len(o) else s,
                  sql=sql)


def answer(eng, question: str):
    """The Answer for a case / customer explain question, or None (then the normal path answers it)."""
    m = match(question)
    if m is None:
        return None
    try:
        return explain_case(eng, m[1]) if m[0] == "case" else explain_customer(eng, m[1])
    except Exception:  # noqa: BLE001 - fall back to the normal path
        return None
