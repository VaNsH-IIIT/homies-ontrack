"""G23: instant answers for common live data questions over gold, deterministic, no LLM (owner: P2).

Judges ask short data questions live: "How many open cases are in each queue?", "What share of open cases carry a
hardship flag?", "How many open cases does OnTrack send to a person first?". These are parsed into
(entity, measure, filters, grouping) and answered with fixed SQL over gold, shown on the page like any other answer.

The parser is deliberately strict: every word of the question must be understood (a measure, an entity, a filter,
a grouping or a filler word), otherwise `parse()` returns None and the question takes the normal path (certified
metric or the Claude agent). This keeps templates away from richer questions, and a guardrail test checks that none
of the released, rehearsal, hard, Layer 1 or C360 questions is captured (their answers can't change).

Entities: open cases (gold.case_360, outcome IS NULL) · golden customers (gold.c360_customer) · OnTrack's
recommendations for open cases (gold.nba_recommendation). French and common typos are normalised first.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

PROVINCES = {"ontario": "ON", "quebec": "QC", "british columbia": "BC", "alberta": "AB", "manitoba": "MB",
             "saskatchewan": "SK", "nova scotia": "NS", "new brunswick": "NB", "newfoundland and labrador": "NL",
             "newfoundland": "NL", "prince edward island": "PE", "yukon": "YT", "northwest territories": "NT",
             "nunavut": "NU"}
PRODUCTS = {"auto loan": "auto_loan", "car loan": "auto_loan", "credit card": "card", "card": "card",
            "mortgage": "mortgage", "personal loan": "personal_loan", "overdraft": "overdraft",
            "line of credit": "loc", "loc": "loc"}
QUEUES = {"early stage": "early_stage", "mid stage": "mid_stage", "late stage": "late_stage",
          "hardship specialist": "hardship_specialist", "special handling": "special_handling",
          "recoveries": "recoveries"}
ACTIONS = {"hardship referral": "hardship_referral", "specialist agent": "specialist_agent", "call": "call",
           "phone call": "call", "sms": "sms", "text message": "sms", "text": "sms", "email": "email",
           "push notification": "push_notification", "reminder letter": "reminder_letter", "letter": "reminder_letter",
           "do nothing": "do_nothing", "no contact": "do_nothing"}
DIMS = {"cases": {"queue": "queue", "province": "province_code", "product": "primary_product",
                  "bucket": "current_bucket"},
        "customers": {"province": "province_code"},
        "recs": {"action": "action", "channel": "channel", "bucket": "current_bucket"}}
TABLES = {"cases": ("gold.case_360", "outcome IS NULL", "open_cases"),
          "customers": ("gold.c360_customer", "", "customers"),
          "recs": ("gold.nba_recommendation", "", "open_cases")}

FRENCH = [(r"\bcombien de\b", "how many"), (r"\bcombien\b", "how many"), (r"\bdossiers? ouverts?\b", "open cases"),
          (r"\bdossiers?\b", "cases"), (r"\bindicateur de difficulte financiere\b", "hardship flag"),
          (r"\bdifficulte financiere\b", "hardship"), (r"\bclients?\b", "customers"), (r"\bont un\b", "have a"),
          (r"\bont\b", "have"), (r"\bsont\b", "are"), (r"\bil y a\b", "there are"), (r"\ben\b", "in"),
          (r"\bpar\b", "by"), (r"\bfile d attente\b", "queue")]
FRENCH_CUE = re.compile(r"\b(combien|dossiers?|clients?|quelle?s?)\b")
FILLER = set("""a an the are is was there do does did we our you of in on at for to be been with have has had that
which what currently right now today so far overall total all any how many much it its they their them this these
those as per by s please tell me show give list currently get""".split())


@dataclass
class Spec:
    entity: str = ""
    measure: str = ""                      # count | total_overdue | share | avg_products | top_action
    filters: list = field(default_factory=list)    # (label, sql condition)
    group: str | None = None
    order: str = "DESC"
    limit: int | None = None
    treat: bool = False                    # "... and how does OnTrack treat them?"


def _norm(q: str) -> str:
    s = unicodedata.normalize("NFKD", q or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9%\s]", " ", s)                       # punctuation, hyphens, apostrophes
    if FRENCH_CUE.search(s):
        for pat, rep in FRENCH:
            s = re.sub(pat, rep, s)
    return " " + " ".join(_fix(w) for w in s.split()) + " "


_VOCAB = {"many", "open", "cases", "case", "customers", "customer", "province", "queue", "hardship", "overdue",
          "ontario", "quebec", "dispute", "complaint", "vulnerable", "golden", "recommend", "ontrack", "share"}


def _fix(w: str) -> str:
    """Typos: a transposition ('mnay') or, for longer words, one wrong letter ('hardshp' stays unmatched)."""
    if w in _VOCAB or w in FILLER or len(w) < 4:
        return w
    for v in _VOCAB:
        if len(v) == len(w) and sorted(v) == sorted(w):
            return v
    return w


def _take(s: str, pat: str) -> tuple[str, re.Match | None]:
    m = re.search(pat, s)
    return (s[:m.start()] + " " + s[m.end():], m) if m else (s, None)


def _alt(d) -> str:
    return "|".join(sorted((re.escape(k) for k in d), key=len, reverse=True))


def parse(question: str) -> Spec | None:
    s, sp = _norm(question), Spec()
    # extras first (their words would otherwise look like entities)
    s, m = _take(s, r" (and )?how (does|do|would) ontrack (treat|handle|deal with) (them|these|those)( customers)? ")
    sp.treat = bool(m)
    s, _ = _take(s, r" in (the )?(customer 360|c360|360) ")
    # measure
    for pat, measure in [(r" (on average )?how many products (does|do) (a |an |each )?(golden )?customers? "
                          r"(hold|have)( on average)? ", "avg_products"),
                         (r" (average|mean) (number of )?products (held )?(per|by|for) (a |each )?(golden )?"
                          r"customers? ", "avg_products"),
                         (r" (what is |what s |which is )?(the )?most (common|frequent) (recommended )?(next best )?"
                          r"action( (and|with) (for )?how many( open)? cases)? ", "top_action"),
                         (r" (what is |what s )?(the )?total (amount )?overdue( amount| balance| dollars)? ", "total_overdue"),
                         (r" (what is |what s )?(the )?(share|percentage|percent|proportion|fraction) of ", "share"),
                         (r" (how many|number of|count of) ", "count")]:
        s, m = _take(s, pat)
        if m:
            sp.measure = measure
            break
    else:
        return None
    if sp.measure == "avg_products":
        sp.entity = "customers"
    # "which province has the highest ..."
    s, m = _take(s, r" which (province|queue|product|bucket|action|channel) (has|have|gets?|sees?) the "
                    r"(highest|most|largest|biggest|lowest|least|fewest|smallest) ")
    if m:
        sp.group, sp.limit = m.group(1), 1
        sp.order = "ASC" if m.group(3) in ("lowest", "least", "fewest", "smallest") else "DESC"
    # generic filters: province, product, queue
    s, m = _take(s, rf" in ({_alt(PROVINCES)}) ")
    if m:
        sp.filters.append(("province", f"province_code = '{PROVINCES[m.group(1)]}'"))
    s, m = _take(s, rf" ({_alt(PRODUCTS)})s? ")
    if m:
        sp.filters.append(("product", f"primary_product = '{PRODUCTS[m.group(1)]}'"))
    s, m = _take(s, rf" in (the )?({_alt(QUEUES)})( queue)? ")
    if m:
        sp.filters.append(("queue", f"queue = '{QUEUES[m.group(2)]}'"))
    # entity: OnTrack's recommendations, open cases, or golden customers
    s, rec_action = _take(s, rf" ({_alt(ACTIONS)})s? (does|do|will|would) ontrack recommend( today| now)? ")
    s, rec_cue = _take(s, r" (does|do|will|would) ontrack (send|route|refer) to a (person|human)( first)? ")
    s, hard_text = _take(s, r" (show|shows|have|has) hardship (in|from) (notes|calls|text|notes or calls|notes and calls"
                            r"|calls or notes)( that)? (the )?(case )?flag (missed|misses|did not catch) ")
    s, ref = _take(s, rf" (get|gets|are given|receive|are sent to)( a| an)? ({_alt(ACTIONS)})s? ")
    s, rec_word = _take(s, r" (does ontrack|ontrack) ")
    if sp.entity != "customers" and (rec_action or rec_cue or hard_text or ref or rec_word or sp.measure == "top_action"):
        sp.entity = "recs"
        if rec_action:
            sp.filters.append(("action", f"action = '{ACTIONS[rec_action.group(1)]}'"))
        if rec_cue:
            sp.filters.append(("to a person", "needs_human_review"))
        if hard_text:
            sp.filters.append(("hardship in text, flag missed", "routing_category = 'hardship_text'"))
        if ref:
            sp.filters.append(("action", f"action = '{ACTIONS[ref.group(3)]}'"))
        s, _ = _take(s, r" (open )?(collections? )?cases? ")
    else:
        s, mc = _take(s, r" (golden )?customers? ")
        if mc or sp.entity == "customers":
            sp.entity = "customers"
            s, m = _take(s, r" (have|has|with) (an |at least one )?open (collections? )?cases? ")
            if m:
                sp.filters.append(("with an open case", "open_case_count > 0"))
        else:
            s, m = _take(s, r" open (collections? )?cases? ")
            if not m:
                return None
            sp.entity = "cases"
    # entity-specific flags
    flags = {"cases": [(r" (carry|carries|have|has|with|show|showing)?( a| an| the)? hardship (flag|flags|indicator) "
                        r"| flagged (for|as) hardship | in hardship ", "hardship flag", "hardship_flag"),
                       (r" (have|has|with)?( an| a)?( open)? disputes?( flag)? | disputed ", "dispute", "dispute_flag"),
                       (r" (have|has|with)?( a| an)? complaints?( flag)? ", "complaint", "complaint_flag"),
                       (r" (flagged )?(as )?vulnerable( customers?)? ", "vulnerable", "vulnerable_customer_flag")],
             "customers": [(r" (are )?(flagged )?(as )?vulnerable | (have|has|with)( a)? vulnerability flag ",
                            "vulnerable", "vulnerability_flag"),
                           (r" (have|has) not (given|provided)( their)? consent to (be called|calls?) "
                            r"| (have|has) no (call )?consent( to (be called|calls?))? "
                            r"| (without|with no) (call )?consent( to (be called|calls?))? ", "no call consent",
                            "NOT consent_call")],
             "recs": [(r" (sent|send|go|goes|routed) to a (person|human)( first)? | (need|needs) human review ",
                       "to a person", "needs_human_review")]}
    for pat, label, cond in flags[sp.entity]:
        s, m = _take(s, pat)
        if m:
            sp.filters.append((label, cond))
    # grouping
    s, m = _take(s, r" (in each|for each|per|by|across|in every) (queue|province|product|bucket|action|channel)s? ")
    if m:
        if sp.group:
            return None
        sp.group = m.group(2)
    if sp.group and sp.group not in DIMS[sp.entity]:
        return None
    # every remaining word must be filler, else this is a richer question: not ours
    left = [w for w in s.split() if w not in FILLER]
    if left:
        return None
    if sp.measure == "share" and not sp.filters:
        return None
    if sp.measure in ("total_overdue",) and sp.entity == "recs":
        return None
    if sp.measure == "avg_products" and sp.entity != "customers":
        return None
    if sp.treat and not (sp.entity == "customers" and any(f[0] == "vulnerable" for f in sp.filters)):
        return None
    return sp


def to_sql(sp: Spec) -> str:
    table, base, count_name = TABLES[sp.entity]
    conds = [base] if base else []
    if sp.measure == "share":                    # the last filter is what we take the share of
        *keep, (label, cond) = sp.filters
        conds += [c for _, c in keep]
        value = f"round(100.0 * avg(CASE WHEN {cond} THEN 1 ELSE 0 END), 1) AS pct_{_col(label)}"
    else:
        conds += [c for _, c in sp.filters]
        value = {"count": f"count(*) AS {count_name}",
                 "total_overdue": "round(sum(total_overdue), 2) AS total_overdue_cad",
                 "avg_products": "round(avg(products_held), 2) AS avg_products_held",
                 "top_action": "count(*) AS open_cases"}[sp.measure]
    where = f" WHERE {' AND '.join(conds)}" if conds else ""
    if sp.measure == "top_action":
        return f"SELECT action, {value} FROM {table}{where} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1"
    if sp.group:
        dim = DIMS[sp.entity][sp.group]
        lim = f" LIMIT {sp.limit}" if sp.limit else ""
        return f"SELECT {dim}, {value} FROM {table}{where} GROUP BY 1 ORDER BY 2 {sp.order}, 1{lim}"
    return f"SELECT {value} FROM {table}{where}"


def treat_sql() -> str:
    return ("SELECT r.action, count(*) AS open_cases, sum(CASE WHEN r.needs_human_review THEN 1 ELSE 0 END) AS "
            "to_a_person_first FROM gold.nba_recommendation r JOIN gold.c360_customer c ON c.golden_id = r.golden_id "
            "WHERE c.vulnerability_flag GROUP BY 1 ORDER BY 2 DESC, 1")


def _col(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def answer(eng, question: str):
    """The Answer for a template question, or None (then the normal path answers it)."""
    sp = parse(question)
    if sp is None:
        return None
    from ontrack.l2_ask.ask import Answer, format_table
    try:
        safe, df = eng.run_sql(to_sql(sp))
        tokens = {"template": f"{sp.entity}.{sp.measure}", "source": TABLES[sp.entity][0]}
        if sp.filters:
            tokens["filters"] = "; ".join(label for label, _ in sp.filters)
        if sp.group:
            tokens["group_by"] = sp.group
        src = safe + f"\n-- sources: [\"{TABLES[sp.entity][0]}\"]"
        if not sp.treat:
            return Answer(format_table(df), src, False, "data", tokens, table=df, sql=safe)
        tsafe, tdf = eng.run_sql(treat_sql())
        n, cases = int(df.iloc[0, 0]), int(tdf["open_cases"].sum())
        human = int(tdf["to_a_person_first"].sum())
        text = (f"{n:,} {'customer is' if n == 1 else 'customers are'} flagged as vulnerable. OnTrack sends {human:,} of their {cases:,} open cases "
                f"({100 * human / max(1, cases):.0f}%) to a person first (hardship team or specialist agent) "
                f"instead of automated contact; the table shows each action.")
        return Answer(text + "\n\n" + format_table(df) + "\n\n" + format_table(tdf),
                      safe + ";\n\n" + tsafe + "\n-- sources: [\"gold.c360_customer\", \"gold.nba_recommendation\"]",
                      False, "explain", tokens, table=tdf, sql=safe + ";\n\n" + tsafe)
    except Exception:  # noqa: BLE001 - fall back to the normal path
        return None
