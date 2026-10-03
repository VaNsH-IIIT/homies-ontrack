"""Scope guard for Ask (owner: P2): runs before any SQL is written.

Check 1 of 3 (design, Layer 2): rules first (fast, deterministic, auditable), then an optional LLM
classifier for what the rules cannot decide. Returns a Verdict: route = data / document / refuse,
with a plain-English reason and an alternative the user can ask instead.
Text inside questions is data, never instructions: nothing here follows instructions in the question.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

def _w(p: str) -> str:
    """Whole words / phrases only ('by agent' must not match 'by age')."""
    return r"\b(?:" + p + r")\b"


PROTECTED_TERMS = {
    "gender": _w(r"gender|sex|male|female|women|woman|men|non-binary"),
    "marital status": _w(r"marital|married|single parents?|divorced|widow(?:ed)?|spouse status"),
    "citizenship": _w(r"citizenship|citizens?|non-citizens?|immigrants?|immigration|permanent residents?|refugees?"),
    "newcomer status": _w(r"newcomers?|new to canada|arrival date|recent arrivals?"),
    "household or dependants": _w(r"household size|dependants?|dependents?|number of (?:kids|children)|"
                                  r"has (?:kids|children)"),
    "accessibility or disability": _w(r"accessibility|disabilit(?:y|ies)|disabled|handicap(?:ped)?"),
    "vulnerability type": _w(r"vulnerability[_ ]type"),
    "child benefit": _w(r"ccb|child benefits?"),
    "accent or ethnicity": _w(r"accents?|ethnicity|ethnic|race|racial|religion|religious|nationality|"
                              r"country of origin"),
    "age": _w(r"age|aged|ages|older customers|younger customers|elderly|seniors?|old people|young people|"
              r"age groups?|age bands?|born (?:in|before|after)|years old|year-olds?|"
              r"(?:customers|people|borrowers|clients) (?:over|under|above|below|aged) \d\d"
              r"(?!\s*(?:\+\s*)?(?:days|dpd|%|percent|cad|\$))"),
}
# Proxies for protected grounds (design: FSA, lat/lon, employer, fsa_income_index stay out of decisions).
PROXY_RE = _w(r"fsas?|forward sortation|postal areas?|postal codes?|postcodes?|neighbou?rhoods?|lat(?:itude)?/lon|"
              r"employer names?|income index|fsa_income_index")
PROTECTED_COLUMNS_RE = _w(r"gender_code|marital_status|citizenship_status|household_size|dependants_count|"
                          r"newcomer_program_flag|newcomer_arrival_date|accessibility_needs_flag|accessibility_type|"
                          r"vulnerability_type|ccb_deposit_flag|customer_accent_region")
PII_TERMS_RE = _w(r"names?|full names?|first names?|last names?|surnames?|phone numbers?|mobile numbers?|"
                  r"email address(?:es)?|emails|home address(?:es)?|street address(?:es)?|mailing address(?:es)?|"
                  r"address(?:es)?|dates? of birth|dobs?|birthdays?|sin|social insurance numbers?|national ids?|"
                  r"card numbers?|contact details|personal details")
PII_INTENT_RE = _w(r"list|export|show|give|get|pull|download|extract|print|dump|send me|provide|share|"
                   r"what (?:is|are)|who (?:is|are)|which customers|look ?up")
PROHIBITED_RE = _w(r"marketing|market to|cross[- ]?sell(?:ing)?|up[- ]?sell(?:ing)?|promotions?|promotional|promote|"
                   r"advertis\w*|credit approvals?|approve (?:a |the |for )?(?:loan|credit|card)s?|underwrit\w*|"
                   r"credit limit increases?|raise (?:their|the) limits?|pre[- ]?approv\w*|re-?identif\w*|"
                   r"de-?anonymi\w*|sell (?:the )?data")
WRITE_RE = r"^\s*(?:please\s+)?(?:delete|drop|update|insert|truncate|alter|create|modify|change|set|remove|" \
           r"overwrite|send|email|text|call)\b"
PRESSURE_RE = (_w(r"chase|pressure|threaten|harass|aggressive(?:ly)?") + r".*"
               + _w(r"hardship|vulnerable|vulnerability|newcomers?|elderly|disabled|immigrants?"))
INJECTION_RE = _w(r"ignore (?:all|previous|the above|your)|system prompt|you are now|jailbreak|"
                  r"disregard (?:your|the|all) (?:rules|instructions)")
# Collections vocabulary: a question with none of these and an obvious off-topic subject is refused.
OFF_TOPIC_RE = _w(r"weather|forecast|temperature|recipe|sports?|hockey|football|movies?|songs?|lyrics|stock price|"
                  r"bitcoin|crypto|horoscope|joke|poem|capital of|who won|translate|write (?:me )?(?:a|an) "
                  r"(?:essay|story|poem)")
DOMAIN_RE = _w(r"cases?|accounts?|customers?|collections?|contacts?|calls?|payments?|promises?|dpd|days past due|"
               r"buckets?|hardship|agents?|queues?|polic(?:y|ies)|cure|roll|arrears|delinquen\w*|disputes?|"
               r"charge[- ]?offs?|write[- ]?offs?|loans?|cards?|deposits?|consent|dialer|transcripts?|notes?")
DOC_RE = _w(r"policy|policies|procedure|guidelines?|according to|documents?|handbook|playbook|script|regulations?|"
            r"rules?|section|faq|code of conduct|data contract|sla|what should|what must|can we|is .* allowed|"
            r"is .* needed|how long|grace period|summari[sz]e|why did")


@dataclass
class Verdict:
    route: str            # "data" | "document" | "refuse"
    reason: str = ""      # why it was refused (plain English), empty when answered
    category: str = ""    # protected | pii | prohibited | write | off_topic | injection
    alternative: str = ""

    @property
    def refused(self) -> bool:
        return self.route == "refuse"


def _refuse(category: str, reason: str, alternative: str) -> Verdict:
    return Verdict("refuse", reason, category, alternative)


def rule_check(question: str) -> Verdict | None:
    """Deterministic refusals. Returns None when the rules cannot decide (then route by content)."""
    q = question.lower()
    if re.search(INJECTION_RE, q):
        return _refuse("injection", "The question asks me to ignore my rules, so I won't answer it.",
                       "Ask a collections question about cases, accounts, contacts or policies.")
    if re.search(PROTECTED_COLUMNS_RE, q):
        return _refuse("protected", "I can't use protected attributes.",
                       "I can break results down by product, province, DPD bucket or hardship signal instead.")
    for label, pattern in PROTECTED_TERMS.items():
        if re.search(pattern, q):
            return _refuse("protected", f"I can't use protected attributes ({label}) as a filter, grouping or driver.",
                           "I can break results down by product, province, DPD bucket or hardship signal instead.")
    if re.search(PROXY_RE, q):           # any use of a proxy for protected grounds (design: proxies stay out)
        return _refuse("protected", "Postal area (FSA), location and employer are proxies for protected grounds "
                       "and income, so I can't use them to decide who gets help or contact.",
                       "I can show hardship-plan outcomes by programme, product or DPD bucket instead.")
    if re.search(PRESSURE_RE, q):
        return _refuse("prohibited", "Hardship and vulnerability raise care, never pressure.",
                       "I can list cases flagged for hardship review so an agent can offer support.")
    if re.search(OFF_TOPIC_RE, q) and not re.search(DOMAIN_RE, q):
        return _refuse("off_topic", "That is outside the scope of collections data and policies.",
                       "Ask about collections cases, accounts, contacts, payments or policies.")
    if re.search(PII_TERMS_RE, q) and re.search(PII_INTENT_RE, q) and not re.search(_w("how many|count|number of|share|rate|average|total"), q):
        return _refuse("pii", "I can't list personal information such as names, contact details or dates of birth.",
                       "I can give counts and aggregates, or case and customer IDs for your assigned work.")
    if re.search(PROHIBITED_RE, q):
        return _refuse("prohibited", "This data is for collections servicing only; marketing, cross-sell and credit "
                       "approval are prohibited uses under our data contract.",
                       "I can answer questions about collections cases, contacts, payments and policies.")
    if re.search(WRITE_RE, q):
        return _refuse("write", "Ask is read-only: it can't change, delete or send anything.",
                       "I can show the current data so you can make the change in the source system.")
    return None


def route(question: str) -> Verdict:
    """Rules first; otherwise data or document by wording (the LLM router refines this when available)."""
    v = rule_check(question)
    if v:
        return v
    return Verdict("document" if re.search(DOC_RE, question.lower()) else "data")
