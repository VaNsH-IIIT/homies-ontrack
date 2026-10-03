"""Ranker: the next best action for every open case, with reasons a person can read (owner: P3).

Order of decisions for each open case (issue #7):

1. **Hardship** (``hardship.py``: case flag, the customer's own words, income shock) -> ``hardship_referral``,
   human-only queue. Only hardship cases can get it.
2. **Needs a person for another reason** (vulnerability, dispute, complaint, holds, cease) -> ``specialist_agent``
   (or ``do_nothing`` if even that is blocked, e.g. deceased), human-only queue.
3. **Likely to pay on its own** (calibrated self-cure chance >= 35%, 3.5x the open book's ~10%) -> ``do_nothing``
   for 7 days, then re-score. Contacting customers who pay anyway costs money and goodwill; in the bank's own
   test cells the no-contact holdout cured as often as the champion strategy (63.4% vs 62.7% within 30 days;
   the holdout was not contact-free, so this is a hint, not proof).
4. **Everyone else**: each contact the policy gate allows is valued as
   ``overdue x (1 - p_cure) x response_rate(channel) x responsiveness - unit_cost``
   with response rates measured from ``contact_history`` (payment within 7 days of an outbound contact) and
   unit costs and call capacity from ``channel_capacity``. ``responsiveness`` is the payment model's score
   relative to the open book (0.5x-2x). Payment links by SMS / email convert ~4x better than calls per
   contact at a fraction of the cost, so digital wins by default. **Calls** go to the cases with the most
   dollars at risk where contact has not worked (2+ contacts in 30 days, no payment, no link clicked) or
   where a call is the only channel allowed, up to the day's call capacity: a conversation is where
   hardship comes out (6.4% of calls vs 0% of digital contacts) and arrangements are made.

Reasons: ``reason_1`` says why this action, with the numbers; ``reason_2`` / ``reason_3`` are the two biggest
drivers of the self-cure estimate (LightGBM SHAP contributions) in business words; ``counterfactual`` says
what would change the recommendation. ``score`` = dollars at risk (overdue x (1 - self-cure chance)), the
queue priority.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from ontrack import config
from ontrack.l3_features.structured.features import PRODUCT_CODES, OPEN_REASON_CODES, TABLE
from ontrack.l4_nba.policy_gate import evaluate, service_notes

SELF_CURE_THRESHOLD = 0.35   # 3.5x the open book's 30-day self-cure rate (~10%): wait a week, then re-score
SPECIALIST_COST_MULTIPLIER = 3.0          # senior agent, longer conversation than a standard call
CONTACT_ACTIONS = {"call": "call", "sms": "sms", "email": "email", "push_notification": "push",
                   "reminder_letter": "letter"}
CHANNEL_OF = {"call": "phone", "sms": "sms", "email": "email", "push_notification": "push",
              "reminder_letter": "letter", "specialist_agent": "phone", "hardship_referral": "human queue",
              "do_nothing": "none"}
ACTION_LABEL = {"call": "Call", "sms": "SMS payment link", "email": "Email payment link",
                "push_notification": "App push with payment link", "reminder_letter": "Reminder letter"}
PEAK_CALL_HOUR = 17     # highest right-party-contact rate in contact_history (70% at 17:00-19:00 local)

PAYMENT_FLAGS = ("coalesce(h.payment_taken_flag, false) OR coalesce(h.link_payment_flag, false) "
                 "OR coalesce(h.app_payment_after_contact_flag, false) "
                 "OR coalesce(h.ivr_self_serve_payment_flag, false)")


# ----------------------------------------------------------------------------------------------------
# Channel economics, measured
# ----------------------------------------------------------------------------------------------------
def channel_economics(con, as_of: str = config.SNAPSHOT_DATE) -> dict:
    """Response rate (payment within 7 days of an outbound contact, last 12 months), unit cost and capacity."""
    rates = con.execute(f"""
        WITH c AS (
            SELECT t.case_id, t.contact_ts_utc AS ts, t.channel
            FROM gold.contact_timeline t JOIN bronze.contact_history h ON h.contact_id = t.contact_id
            WHERE h.direction = 'outbound' AND t.case_id IS NOT NULL
              AND t.contact_ts_utc >= DATE '{as_of}' - INTERVAL 1 YEAR AND t.contact_ts_utc < DATE '{as_of}'
        ),
        p AS (
            SELECT t.case_id, t.contact_ts_utc AS ts
            FROM gold.contact_timeline t JOIN bronze.contact_history h ON h.contact_id = t.contact_id
            WHERE t.case_id IS NOT NULL AND ({PAYMENT_FLAGS})
        )
        SELECT c.channel, count(*) AS n,
               round(avg((p.ts IS NOT NULL AND p.ts < c.ts + INTERVAL 7 DAY)::INT), 6) AS rate
        FROM c ASOF LEFT JOIN p ON c.case_id = p.case_id AND p.ts >= c.ts
        GROUP BY 1
    """).fetchdf().set_index("channel")
    cap = con.execute("""
        SELECT channel, sum(capacity_units) AS capacity, avg(unit_cost_cad) AS unit_cost
        FROM bronze.channel_capacity
        WHERE date = (SELECT max(date) FROM bronze.channel_capacity) AND NOT coalesce(outage_flag, false)
        GROUP BY 1
    """).fetchdf().set_index("channel")
    out = {}
    for action, ch in CONTACT_ACTIONS.items():
        out[action] = {"rate": float(rates["rate"].get(ch, 0.0)), "contacts": int(rates["n"].get(ch, 0)),
                       "unit_cost": float(cap["unit_cost"].get(ch, 0.0)),
                       "capacity": int(cap["capacity"].get(ch, 0))}
    out["specialist_agent"] = {"rate": out["call"]["rate"], "contacts": out["call"]["contacts"],
                               "unit_cost": out["call"]["unit_cost"] * SPECIALIST_COST_MULTIPLIER, "capacity": 0}
    return out


# ----------------------------------------------------------------------------------------------------
# Reasons in business words
# ----------------------------------------------------------------------------------------------------
PRODUCT_NAMES = {v: k.replace("_", " ") for k, v in PRODUCT_CODES.items()}
REASON_NAMES = {1: "a missed payment", 2: "a returned pre-authorised payment", 3: "going over the limit",
                4: "a manual referral"}
_ = OPEN_REASON_CODES  # codes defined next to the feature SQL


def _n(v) -> int:
    return int(round(float(v)))


def _fact(f: str, v: float) -> str | None:
    """A plain statement of the feature value with whole numbers, or None when not worth showing."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    never = v >= 999
    facts = {
        "case_age_days": f"In collections for {_n(v)} days",
        "overdue_now": f"${v:,.0f} overdue now",
        "entry_overdue": f"${v:,.0f} overdue when the case opened",
        "overdue_growth_pct": (f"Arrears up {v:.0%} since the case opened" if v > 0.005
                               else "Arrears have not grown since the case opened"),
        "prior_cases_12m": (f"{_n(v)} earlier collections case{'s' if _n(v) != 1 else ''} in the past 12 months"
                            if v >= 1 else "First collections case in 12 months"),
        "product_code": f"{PRODUCT_NAMES.get(_n(v), 'other').capitalize()} account",
        "open_reason_code": f"Case opened after {REASON_NAMES.get(_n(v), 'a missed payment')}",
        "other_open_cases": (f"Also behind on {_n(v)} other case{'s' if _n(v) != 1 else ''}" if v >= 1
                             else "No other open collections case"),
        "contacts_total": f"{_n(v)} contacts on this case so far",
        "contacts_30d": f"{_n(v)} contacts in the last 30 days",
        "contacts_7d": f"{_n(v)} contacts in the last 7 days",
        "inbound_30d": (f"Customer contacted us {_n(v)} time{'s' if _n(v) != 1 else ''} in the last 30 days"
                        if v >= 1 else "Customer has not contacted us in the last 30 days"),
        "rpc_30d": f"Reached the customer {_n(v)} time{'s' if _n(v) != 1 else ''} in the last 30 days",
        "rpc_rate_30d": f"Answered {v:.0%} of contact attempts in the last 30 days",
        "days_since_last_contact": ("Not contacted on this case yet" if never
                                    else f"Last contact {_n(v)} days ago"),
        "days_since_last_rpc": ("Never reached in person on this case" if never
                                else f"Last spoke with the customer {_n(v)} days ago"),
        "payments_total": f"{_n(v)} payment{'s' if _n(v) != 1 else ''} on this case so far",
        "payments_30d": f"{_n(v)} payment{'s' if _n(v) != 1 else ''} in the last 30 days",
        "payment_amount_90d": f"${v:,.0f} paid in the last 90 days",
        "days_since_last_payment": ("No payment on this case yet" if never
                                    else f"Last payment {_n(v)} days ago"),
        "link_clicks_30d": (f"Opened a payment link {_n(v)} time{'s' if _n(v) != 1 else ''} in the last 30 days"
                            if v >= 1 else "Has not opened a payment link in the last 30 days"),
        "callback_requested_30d": f"Asked for a call back {_n(v)} time{'s' if _n(v) != 1 else ''} in 30 days",
        "hardship_mentioned_any": ("Mentioned money trouble on a past call" if v >= 1
                                   else "No money trouble mentioned on past contacts"),
        "dispute_raised_any": "Raised a dispute on a past contact" if v >= 1 else "No dispute raised",
        "bureau_score": f"Credit bureau score {_n(v)}",
        "bureau_utilisation": f"Using {v:.0%} of revolving credit at other lenders",
        "bureau_delinquent_trades": (f"{_n(v)} account{'s' if _n(v) != 1 else ''} in arrears at other lenders"
                                     if v >= 1 else "No arrears at other lenders"),
        "bureau_inquiries_6m": f"{_n(v)} credit application{'s' if _n(v) != 1 else ''} in the last 6 months",
        "bureau_age_days": f"Credit bureau data from {_n(v)} days ago",
        "salary_gap_months_3m": (f"Salary missing or late in {_n(v)} of the last 3 months" if v >= 1
                                 else "Salary arrived on time for the last 3 months"),
        "salary_drop_pct": (f"Income down {abs(v):.0%} on the previous 6 months" if v < -0.05 else
                            f"Income up {v:.0%} on the previous 6 months" if v > 0.05
                            else "Income steady over the last 9 months"),
        "has_payroll": "Salary paid into an account with us" if v >= 1 else "No salary deposits with us",
        "acct_months_min_paid_6m": f"Paid at least the minimum in {_n(v)} of the last 6 statements",
        "acct_utilisation": f"Using {v:.0%} of credit limits with us",
        "acct_max_dpd": f"{_n(v)} days past due on the worst account two months ago",
        "acct_overlimit": "Over the credit limit two months ago" if v >= 1 else "Within credit limits",
    }
    return facts.get(f)


# feature -> (why when it raises the self-cure chance, why when it lowers it,
#             value check for the first, value check for the second). A custom phrase is only used when
#             the value agrees with it; otherwise the neutral phrase is used, so a reason never contradicts
#             its own number.
_WHY = {
    "case_age_days": ("most cases this new pay on their own", "the longer a case runs, the less it clears on its own",
                      lambda v: v <= 30, lambda v: v > 30),
    "overdue_now": ("small enough to clear on its own", "larger arrears rarely clear without help",
                    lambda v: v < 300, lambda v: v >= 300),
    "acct_months_min_paid_6m": ("a habit of paying", "has missed minimum payments before",
                                lambda v: v >= 4, lambda v: v <= 3),
    "bureau_delinquent_trades": ("not behind elsewhere", "stretched across lenders",
                                 lambda v: v < 1, lambda v: v >= 1),
    "bureau_inquiries_6m": ("not looking for new credit", "looking for credit, a sign of strain",
                            lambda v: v <= 1, lambda v: v >= 2),
    "salary_gap_months_3m": ("steady income", "income interrupted", lambda v: v < 1, lambda v: v >= 1),
    "salary_drop_pct": ("income holding up", "less money coming in", lambda v: v >= -0.05, lambda v: v < -0.05),
    "inbound_30d": ("engaged with us", "not engaging with us", lambda v: v >= 1, lambda v: v < 1),
    "link_clicks_30d": ("responds to digital reminders", "digital reminders are not working",
                        lambda v: v >= 1, lambda v: v < 1),
    "days_since_last_payment": ("paying recently", "no recent payment", lambda v: v <= 30, lambda v: v > 30),
    "hardship_mentioned_any": ("no sign of money trouble", "a sign it may not clear on its own",
                               lambda v: v < 1, lambda v: v >= 1),
    "prior_cases_12m": ("no history of arrears", "repeat arrears", lambda v: v < 1, lambda v: v >= 1),
    "bureau_score": ("good credit standing", "weak credit standing", lambda v: v >= 680, lambda v: v < 620),
    "entry_overdue": ("small enough to clear on its own", "larger arrears rarely clear without help",
                      lambda v: v < 300, lambda v: v >= 300),
    "overdue_growth_pct": ("not getting worse", "getting worse", lambda v: v <= 0.005, lambda v: v > 0.05),
    "bureau_utilisation": ("room to pay", "stretched for credit", lambda v: v < 0.5, lambda v: v >= 0.7),
    "acct_utilisation": ("room to pay", "close to the limit", lambda v: v < 0.5, lambda v: v >= 0.8),
    "payments_total": ("already paying", "no payment yet", lambda v: v >= 1, lambda v: v < 1),
    "payments_30d": ("already paying", "no recent payment", lambda v: v >= 1, lambda v: v < 1),
    "payment_amount_90d": ("already paying", "nothing paid recently", lambda v: v > 0, lambda v: v <= 0),
    "rpc_rate_30d": ("reachable", "hard to reach", lambda v: v >= 0.5, lambda v: v < 0.2),
    "days_since_last_rpc": ("in touch recently", "hard to reach", lambda v: v <= 14, lambda v: v >= 60),
    "contacts_total": ("", "repeated contact has not cleared it", lambda v: False, lambda v: v >= 3),
    "contacts_30d": ("", "repeated contact has not cleared it", lambda v: False, lambda v: v >= 3),
    "other_open_cases": ("", "behind on more than one case", lambda v: False, lambda v: v >= 1),
    "acct_max_dpd": ("", "already behind before this case", lambda v: False, lambda v: v >= 30),
}


def _why(f: str, up: bool, v: float | None = None) -> str | None:
    """Why the fact matters, or None when the direction would read counter-intuitively to an agent
    (e.g. 'income up 132%' lowering the self-cure chance): such drivers are not shown with a why."""
    if f in _WHY and v is not None:
        up_txt, down_txt, up_ok, down_ok = _WHY[f]
        if up and up_txt and up_ok(v):
            return up_txt
        if not up and down_ok(v):
            return down_txt
    return None


# Model inputs that mean nothing to an agent: used by the model, never shown as a reason.
HIDDEN_DRIVERS = {"bureau_age_days"}


# Facts that are fine to show as plain context (no direction claimed) when a case has too few intuitive drivers
CONTEXT_FACTS = ["overdue_now", "case_age_days", "contacts_30d", "days_since_last_payment", "bureau_score"]


def driver_reasons(shap_row: np.ndarray, values: dict, cols: list[str], k: int = 2) -> list[tuple[str, str, bool]]:
    """Top-k drivers as (feature, sentence, raises_cure_chance).

    Only drivers whose why reads naturally for their value are shown, strongest first; if fewer than k, the
    reasons are filled with plain context facts (no why), so every recommendation still has three reasons.
    """
    out, used = [], set()
    for i in np.argsort(-np.abs(shap_row)):
        f = cols[i]
        if f in HIDDEN_DRIVERS or abs(shap_row[i]) < 1e-6:
            continue
        fact = _fact(f, values.get(f))
        if fact is None:
            continue
        up = bool(shap_row[i] > 0)
        why = _why(f, up, float(values.get(f)))
        if why is None:
            continue
        out.append((f, f"{fact}: {why}", up))
        used.add(f)
        if len(out) == k:
            return out
    for f in CONTEXT_FACTS:
        if len(out) == k:
            break
        fact = _fact(f, values.get(f)) if f not in used and f in cols else None
        if fact:
            i = cols.index(f)
            out.append((f, fact, bool(shap_row[i] > 0)))
    return out


COUNTERFACTUALS = {
    "days_since_last_payment": "a payment arrives",
    "payments_30d": "a payment arrives",
    "acct_months_min_paid_6m": "the customer pays at least the minimum this month",
    "link_clicks_30d": "the customer opens a payment link",
    "inbound_30d": "the customer gets in touch",
    "overdue_now": "the overdue amount falls",
    "salary_gap_months_3m": "salary deposits resume",
    "salary_drop_pct": "income recovers",
}


def counterfactual(action: str, drivers: list[tuple[str, str, bool]], p_cure: float, as_of: dt.date) -> str:
    if action == "hardship_referral":
        return "Automated contact resumes only after a person has reviewed the hardship and agreed a plan"
    if action == "specialist_agent":
        return "Goes back to automated treatment only once a person clears the flag"
    if action == "do_nothing":
        return f"Would switch to a contact if no payment arrives by {(as_of + dt.timedelta(days=7)).isoformat()}"
    for f, _, up in drivers:
        if not up and f in COUNTERFACTUALS:
            return f"Would switch to no contact if {COUNTERFACTUALS[f]} (self-cure chance now {_pct(p_cure)})"
    return f"Would switch to no contact if the self-cure chance rose above {SELF_CURE_THRESHOLD:.0%} (now {_pct(p_cure)})"


# ----------------------------------------------------------------------------------------------------
# Ranking
# ----------------------------------------------------------------------------------------------------
CHARGE_OFF_DPD = 180   # every charged-off case in the release was charged off at 181 DPD; open cases top out at 180


def roll_forward_columns(p_cure: float, dpd) -> tuple[float | None, float | None]:
    """(p_roll_forward, p_charge_off_risk) for one case.

    DPD rises by one a day until a case cures, so not curing within 30 days means rolling to the next 30-day
    bucket, unless that takes the case past 180 DPD: then the next step is charge-off, not a worse bucket,
    and the same chance of staying unpaid is its charge-off risk. (The source `current_bucket` label '180+' is
    not used: most open cases carrying it are below 180 DPD.)
    """
    risk = round(1 - float(p_cure), 4)
    if dpd is not None and not pd.isna(dpd) and float(dpd) + 30 > CHARGE_OFF_DPD:
        return None, risk
    return risk, None


def risk_rank(raw_self_cure: np.ndarray, case_ids) -> np.ndarray:
    """1 = most likely to stay unpaid. Uses the raw model score, which keeps the model's resolution (~84K distinct
    values on the open book) where the calibrated probabilities tie in ~120 steps; ties go to case_id."""
    order = sorted(range(len(case_ids)), key=lambda i: (round(float(raw_self_cure[i]), 9), str(case_ids[i])))
    rank = np.empty(len(case_ids), dtype=np.int64)
    rank[order] = np.arange(1, len(case_ids) + 1)
    return rank


def contact_values(overdue: float, p_cure: float, responsiveness: float, allowed: list[str], econ: dict) -> dict:
    """Expected net value (CAD) of each allowed contact action versus doing nothing."""
    return {a: overdue * (1 - p_cure) * econ[a]["rate"] * responsiveness - econ[a]["unit_cost"]
            for a in allowed if a in CONTACT_ACTIONS}


def choose_action(row: dict, allowed: list[str], values: dict) -> tuple[str, str]:
    """Pick the action before call capacity is applied. Returns (action, decision path)."""
    if row["hardship_flag"]:
        return "hardship_referral", "hardship"
    if row["needs_human_review"]:
        return ("specialist_agent" if "specialist_agent" in allowed else "do_nothing"), "human"
    if row["p_cure"] >= SELF_CURE_THRESHOLD:
        return "do_nothing", "self_cure"
    if not values or max(values.values()) <= 0:
        return "do_nothing", "not_worth_contact"
    best = max(values, key=values.get)
    return best, "value"


def wants_call(row: dict, allowed: list[str], values: dict) -> bool:
    """Call candidates (capacity-limited): contact has not worked, or a call is the best allowed channel."""
    if "call" not in allowed or row["path"] != "value":
        return False
    no_response = row["contacts_30d"] >= 2 and row["payments_30d"] == 0 and row["link_clicks_30d"] == 0
    return no_response or row["action"] == "call"


def action_values_text(values: dict) -> str | None:
    """Expected net value (CAD, vs doing nothing) of every allowed contact, best first, for the agent card."""
    if not values:
        return None
    parts = [f"{a}: {'-' if v < 0 else ''}${abs(v):,.2f}" for a, v in sorted(values.items(), key=lambda x: (-x[1], x[0]))]
    return "; ".join(parts + ["do_nothing: $0.00"])


def _pct(p: float) -> str:
    return "under 1%" if p < 0.005 else "over 99%" if p > 0.995 else f"{p:.0%}"


def _cad(x: float) -> str:
    return "under 1 cent" if x < 0.01 else f"${x:.2f}"


def _time_window(action: str, best_hour) -> str:
    if action in ("call", "specialist_agent"):
        h = int(best_hour) if best_hour is not None and not pd.isna(best_hour) and 8 <= best_hour <= 19 else PEAK_CALL_HOUR
        return f"{h:02d}:00-{h + 2:02d}:00 local (customer answers most at this time)" if h != PEAK_CALL_HOUR \
            else f"{h:02d}:00-{h + 2:02d}:00 local (best answer rate)"
    if action in ("sms", "email", "push_notification"):
        return "09:00-12:00 local"
    if action == "reminder_letter":
        return "next mailing day"
    if action == "hardship_referral":
        return "within 1 business day"
    return "review again in 7 days"


def _reason_1(r: dict, econ: dict) -> str:
    a, p, amt = r["action"], r["p_cure"], r["overdue_now"]
    if a == "hardship_referral":
        quote = str(r.get("text_evidence") or "").strip()
        if quote and r.get("routing_category") != "hardship_text":   # add the customer's own words
            quote = quote if len(quote) <= 120 else quote[:117].rstrip() + "..."
            return f'Hardship: {r["routing_reason"]}; the customer said "{quote}"'
        return f"Hardship: {r['routing_reason']}"
    if a == "specialist_agent":
        return f"Needs a person: {r['routing_reason']}"
    if a == "do_nothing" and r["path"] == "self_cure":
        return (f"Likely to pay without contact: self-cure chance {_pct(p)} in 30 days, 3.5x the open-book "
                f"average; contacting now would cost money and goodwill for little gain")
    if a == "do_nothing" and r["path"] == "call_queue_full":
        return (f"Call needed but today's {econ['call']['capacity']:,} call slots went to cases with more at stake, "
                f"and no other channel is allowed: first in line for tomorrow's calls")
    if a == "do_nothing" and r["path"] == "human":
        return f"Needs a person, no contact allowed: {r['routing_reason']}"
    if a == "do_nothing" and not any(x in CONTACT_ACTIONS for x in r["allowed"]):
        why = next((v[0] for k in ("sms", "email", "call") for v in [r["blocked"].get(k)] if v), "policy")
        return f"No contact allowed today ({why}); review again in 7 days"
    if a == "do_nothing":
        return f"Not worth a contact: ${amt:,.0f} overdue, every allowed channel costs more than it is likely to recover"
    risk = f"{_pct(1 - p)} chance the ${amt:,.0f} stays unpaid without action"
    if a == "call":
        why = ("contact in the last 30 days brought no payment and no link was opened; a conversation is "
               "where arrangements are made and hardship comes out") if r["call_reason"] == "no_response" \
            else "the best channel the customer has allowed us to use"
        return f"Call: {risk}; {why}"
    e = econ[a]
    if a == "reminder_letter":
        return (f"Reminder letter: {risk}; no digital channel or call slot available, and a letter "
                f"(payment within 7 days after {e['rate']:.0%}, {_cad(e['unit_cost'])}) is still worth sending")
    extra = " (call queue full today)" if r["path"] == "call_queue_full" else ""
    return (f"{ACTION_LABEL[a]}{extra}: {risk}; links bring a payment within 7 days after {e['rate']:.0%} of "
            f"contacts at {_cad(e['unit_cost'])} each (calls {econ['call']['rate']:.0%} at {_cad(econ['call']['unit_cost'])})")


def build_recommendations(con, routed: pd.DataFrame, as_of: str = config.SNAPSHOT_DATE) -> pd.DataFrame:
    """Score, route and rank every open case; returns the recommendation frame."""
    from ontrack.l4_nba.models import load_model, predict

    as_of_date = dt.date.fromisoformat(as_of)
    contact_day = as_of_date + dt.timedelta(days=1)   # recommendations are for the next working day
    contact_ts = dt.datetime.combine(contact_day, dt.time(12, 0))

    feats = con.execute(f"""
        SELECT f.*,
               cu.consent_call, cu.consent_sms, cu.consent_email, cu.consent_push, cu.consent_autodialer,
               cu.internal_do_not_call_flag, cu.preferred_language,
               coalesce(cu.cease_communication_flag, false) OR coalesce(c.cease_contact_flag, false) AS cease_communication_flag,
               coalesce(cu.insolvency_flag, false) OR coalesce(c.insolvency_hold_flag, false) AS insolvency_flag,
               coalesce(cu.deceased_flag, false) OR coalesce(c.deceased_hold_flag, false) AS deceased_flag,
               coalesce(cu.third_party_hold_flag, false) OR coalesce(c.third_party_rep_flag, false) AS third_party_hold_flag,
               coalesce(c.dispute_flag, false) AS dispute_flag, c.current_bucket_derived AS current_bucket,
               c.current_dpd,
               coalesce(cu.vulnerability_flag, false) OR coalesce(c.vulnerable_customer_flag, false) AS vulnerability_flag,
               coalesce(c.contacts_last_7d, 0) AS contacts_last_7d, coalesce(c.contact_cap_7d, 7) AS contact_cap_7d
        FROM {TABLE} f
        JOIN gold.case_360 c ON c.case_id = f.case_id
        LEFT JOIN gold.c360_customer cu ON cu.golden_id = f.golden_id
        WHERE f.as_of_date = DATE '{as_of}'
        ORDER BY f.case_id
    """).fetchdf()
    df = feats.merge(routed, on="case_id", how="left", validate="one_to_one")
    for col in ("hardship_flag", "needs_human_review"):
        df[col] = df[col].fillna(False).astype(bool)

    m_cure, m_pay = load_model("self_cure_30d"), load_model("payment_7d")
    cols = m_cure["feature_cols"]
    df["p_cure"] = predict(m_cure, df)
    raw_cure = m_cure["booster"].predict(np.round(df[cols].astype(float).to_numpy(), 6))
    df["model_risk_rank"] = risk_rank(raw_cure, df["case_id"].tolist())
    df["p_payment"] = predict(m_pay, df)
    resp = (df["p_payment"] / max(df["p_payment"].mean(), 1e-6)).clip(0.5, 2.0).round(6)
    contrib = m_cure["booster"].predict(np.round(df[cols].astype(float).to_numpy(), 6), pred_contrib=True)[:, :-1]
    econ = channel_economics(con, as_of)

    records = df.to_dict("records")
    rows = []
    for i, r in enumerate(records):
        r = {k: (None if (not isinstance(v, (list, dict, str)) and pd.isna(v)) else v) for k, v in r.items()}
        r["hardship_flag"] = bool(r["hardship_flag"])
        r["needs_human_review"] = bool(r["needs_human_review"])
        gate = evaluate(r, contact_ts)
        allowed = [a for a, g in gate.items() if g.allowed]
        if not r["hardship_flag"]:
            allowed = [a for a in allowed if a != "hardship_referral"]   # hardship_referral is for hardship only
        blocked = {a: g.reasons for a, g in gate.items() if not g.allowed}
        values = contact_values(float(r["overdue_now"] or 0), float(r["p_cure"]), float(resp.iat[i]), allowed, econ)
        action, path = choose_action(r, allowed, values)
        r.update(action=action, path=path, allowed=allowed, blocked=blocked, values=values,
                 expected_loss=round(float(r["overdue_now"] or 0) * (1 - float(r["p_cure"])), 6))
        r["call_candidate"] = wants_call(r, allowed, values)
        r["shap_i"] = i
        rows.append(r)

    # Call capacity: the day's call slots go to the candidates with the most dollars at risk
    call_capacity = econ["call"]["capacity"]
    cands = sorted((r for r in rows if r["call_candidate"]), key=lambda r: (-r["expected_loss"], r["case_id"]))
    for rank, r in enumerate(cands):
        if rank < call_capacity:
            r["call_reason"] = "best_channel" if r["action"] == "call" else "no_response"
            r["action"] = "call"
        elif r["action"] == "call":   # over capacity: best other channel, or first in line tomorrow
            others = {a: v for a, v in r["values"].items() if a != "call" and v > 0}
            r["action"] = max(others, key=others.get) if others else "do_nothing"
            r["path"] = "call_queue_full"
    for r in rows:
        r.setdefault("call_reason", None)
    assert sum(r["action"] == "call" for r in rows) <= call_capacity, "call capacity exceeded"

    out = []
    for r in rows:
        values_f = {c: r.get(c) for c in cols}
        drivers = driver_reasons(contrib[r["shap_i"]], values_f, cols)
        reasons = [_reason_1(r, econ)] + [d[1] for d in drivers]
        notes = service_notes(r) if r["action"] in ("call", "specialist_agent") else []
        out.append({
            "case_id": r["case_id"], "golden_id": r["golden_id"],
            "as_of_ts": dt.datetime.combine(as_of_date, dt.time(0, 0)),
            "action": r["action"], "channel": CHANNEL_OF[r["action"]],
            "time_window": _time_window(r["action"], r.get("best_rpc_hour")),
            "score": round(r["expected_loss"], 2),
            "reason_1": reasons[0], "reason_2": reasons[1] if len(reasons) > 1 else None,
            "reason_3": reasons[2] if len(reasons) > 2 else None,
            "counterfactual": counterfactual(r["action"], drivers, float(r["p_cure"]), as_of_date),
            "blocked_actions": ", ".join(sorted(r["blocked"])) or None,
            "blocked_reasons": "; ".join(f"{a}: {' / '.join(v)}" for a, v in sorted(r["blocked"].items())) or None,
            "allowed_actions": ", ".join(r["allowed"]),
            "service_notes": "; ".join(notes) or None,
            "hardship_flag": r["hardship_flag"], "needs_human_review": r["needs_human_review"],
            "routing_category": r.get("routing_category"), "routing_reason": r.get("routing_reason"),
            "routing_reasons": r.get("routing_reasons"),
            "text_evidence": r.get("text_evidence"), "text_source": r.get("text_source"),
            "p_cure_30d": round(float(r["p_cure"]), 4), "p_payment_7d": round(float(r["p_payment"]), 4),
            # the names match what Layer 2's roll-forward question looks for (R5, #5); see roll_forward_columns
            "current_bucket": r.get("current_bucket"),
            "current_dpd": r.get("current_dpd"),
            "p_roll_forward": roll_forward_columns(r["p_cure"], r.get("current_dpd"))[0],
            "p_charge_off_risk": roll_forward_columns(r["p_cure"], r.get("current_dpd"))[1],
            # tie-break for both lists: the calibrated probabilities tie (24K cases at ~1.0), the raw score does not
            "model_risk_rank": int(r["model_risk_rank"]),
            "overdue_now": round(float(r["overdue_now"] or 0), 2),
            "expected_value": round(float(r["values"].get(r["action"], 0.0)), 2),
            "action_values": action_values_text(r["values"]),
            "decision_path": r["path"], "model_version": m_cure["meta"]["model_version"],
        })
    rec = pd.DataFrame(out)
    con.execute("CREATE OR REPLACE TABLE gold.nba_recommendation AS SELECT * FROM rec")
    return rec


def print_summary(rec: pd.DataFrame, econ: dict | None = None) -> None:
    n = len(rec)
    print(f"gold.nba_recommendation  {n:,} rows")
    mix = rec["action"].value_counts()
    for a, k in mix.items():
        print(f"  {a:20s} {k:>7,}  ({k / n:.1%})")
    print(f"  human-only queue: {int(rec['needs_human_review'].sum()):,} ({rec['needs_human_review'].mean():.0%})")
    if econ:
        print("  channel economics (payment within 7 days of a contact, last 12 months):")
        for a, e in econ.items():
            print(f"    {a:18s} rate {e['rate']:.1%}  cost ${e['unit_cost']:.3f}  capacity {e['capacity']:,}")
