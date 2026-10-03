"""Ranker: pick the best allowed action for each open case (owner: P3).

For each case:
  1. Policy gate → allowed/blocked actions
  2. Score allowed actions with models
  3. Rank by expected net value (recovery - cost)
  4. Generate top-3 SHAP reasons in plain English
  5. Write gold.nba_recommendation and l4.decision_log
"""
from __future__ import annotations

import datetime as dt
import uuid

import numpy as np
import shap

from ontrack import config
from ontrack.l4_nba.policy_gate import evaluate, needs_human_review, ACTIONS

MODEL_VERSION = "v0.1"

ACTION_COSTS = {
    "do_nothing": 0.0,
    "call": 8.50,
    "sms": 0.15,
    "email": 0.05,
    "push_notification": 0.03,
    "reminder_letter": 2.00,
    "hardship_referral": 0.0,
    "specialist_agent": 15.00,
}

ACTION_RECOVERY_MULTIPLIER = {
    "do_nothing": 0.3,
    "call": 1.0,
    "sms": 0.6,
    "email": 0.5,
    "push_notification": 0.4,
    "reminder_letter": 0.7,
    "hardship_referral": 0.8,
    "specialist_agent": 1.2,
}

REASON_TEMPLATES = {
    "dpd_current": "Currently {value} days past due",
    "past_due_max": "Maximum past-due amount is ${value:,.0f}",
    "total_past_due": "Total past-due across accounts is ${value:,.0f}",
    "past_due_ratio": "Past-due is {value:.0%} of total balance",
    "days_since_last_payment": "No payment in {value} days",
    "payments_90d": "{value} payments in the last 90 days",
    "payments_30d": "{value} payments in the last 30 days",
    "rpc_rate_30d": "Right-party contact rate is {value:.0%} in the last 30 days",
    "contacts_30d": "{value} contact attempts in the last 30 days",
    "contacts_7d": "{value} contacts in the last 7 days",
    "case_age_days": "Case has been open for {value} days",
    "bureau_score_current": "Bureau score is {value}",
    "score_delta_90d": "Bureau score changed by {value} in the last 90 days",
    "utilisation_current": "Credit utilisation is {value:.0%}",
    "total_balance": "Total balance is ${value:,.0f}",
    "total_exposure": "Total exposure is ${value:,.0f}",
    "n_accounts": "Customer has {value} accounts",
    "open_case_count": "{value} open collection cases",
    "dpd_at_entry": "DPD was {value} at case entry",
    "rpc_count": "{value} right-party contacts total",
    "total_contacts": "{value} total contacts on this case",
    "accounts_30dpd": "{value} accounts are 30+ days past due",
    "inquiries_hard_3m": "{value} hard credit inquiries in the last 3 months",
    "products_held": "Customer holds {value} products",
    "total_overdue": "Total overdue amount is ${value:,.0f}",
}


COUNTERFACTUAL_TEMPLATES = {
    "dpd_current": "Would improve if DPD dropped below {threshold}",
    "past_due_max": "Would improve if past-due amount fell below ${threshold:,.0f}",
    "total_past_due": "Would improve if total past-due fell below ${threshold:,.0f}",
    "past_due_ratio": "Would improve if past-due ratio dropped below {threshold:.0%}",
    "days_since_last_payment": "Would change if a payment were made within {threshold} days",
    "payments_90d": "Would improve with at least {threshold} payments in 90 days",
    "payments_30d": "Would improve with at least {threshold} payment in 30 days",
    "rpc_rate_30d": "Would improve if RPC rate exceeded {threshold:.0%}",
    "contacts_30d": "Would change if contact frequency adjusted to {threshold}",
    "bureau_score_current": "Would improve if bureau score rose above {threshold}",
    "case_age_days": "Would change if resolved within {threshold} days",
}

COUNTERFACTUAL_THRESHOLDS = {
    "dpd_current": 30, "past_due_max": 500, "total_past_due": 1000,
    "past_due_ratio": 0.1, "days_since_last_payment": 30, "payments_90d": 2,
    "payments_30d": 1, "rpc_rate_30d": 0.5, "contacts_30d": 3,
    "bureau_score_current": 650, "case_age_days": 60,
}


def _format_reason(feature_name: str, feature_value: float, shap_value: float) -> str:
    """Turn a SHAP feature into a plain-English reason."""
    template = REASON_TEMPLATES.get(feature_name)
    if template:
        try:
            fact = template.format(value=feature_value)
        except (ValueError, KeyError):
            fact = f"{feature_name} = {feature_value}"
    else:
        fact = f"{feature_name} = {feature_value}"
    return fact


def _counterfactual(feature_name: str) -> str | None:
    """Generate a 'would change if…' line for the top driver."""
    tmpl = COUNTERFACTUAL_TEMPLATES.get(feature_name)
    threshold = COUNTERFACTUAL_THRESHOLDS.get(feature_name)
    if tmpl and threshold is not None:
        try:
            return tmpl.format(threshold=threshold)
        except (ValueError, KeyError):
            pass
    return None


def get_shap_reasons(
    model_dict: dict,
    features_row: np.ndarray,
    feature_values: dict[str, float],
    top_n: int = 3,
    include_counterfactual: bool = True,
) -> list[str]:
    """Get top-N SHAP-based reasons for a prediction, with optional counterfactual."""
    booster = model_dict["booster"]
    feature_cols = model_dict["feature_cols"]
    explainer = shap.TreeExplainer(booster)
    shap_values = explainer.shap_values(features_row.reshape(1, -1))[0]

    indices = np.argsort(np.abs(shap_values))[::-1][:top_n]
    reasons = []
    for idx in indices:
        fname = feature_cols[idx]
        fval = feature_values.get(fname, features_row[idx])
        reasons.append(_format_reason(fname, fval, shap_values[idx]))

    if include_counterfactual and len(indices) > 0:
        top_fname = feature_cols[indices[0]]
        cf = _counterfactual(top_fname)
        if cf:
            reasons.append(cf)

    return reasons


def rank_actions(
    case_row: dict,
    p_cure: float,
    p_payment: float,
    expected_amount: float,
    allowed_actions: list[str],
) -> list[tuple[str, float]]:
    """Rank allowed actions by net expected value."""
    scored = []
    for action in allowed_actions:
        multiplier = ACTION_RECOVERY_MULTIPLIER.get(action, 0.5)
        cost = ACTION_COSTS.get(action, 0.0)
        if action == "do_nothing":
            ev = p_cure * expected_amount * multiplier
        else:
            ev = p_payment * expected_amount * multiplier - cost
        scored.append((action, ev))
    scored.sort(key=lambda x: -x[1])
    return scored


def recommend_for_case(
    case_row: dict,
    features_row: np.ndarray,
    feature_values: dict[str, float],
    model_cure: dict,
    model_payment: dict | None,
    as_of_ts: dt.datetime | None = None,
) -> dict:
    """Generate the NBA recommendation for one case."""
    from ontrack.l4_nba.models import predict
    import pandas as pd

    feature_cols_cure = model_cure["feature_cols"]
    cure_features = np.array([feature_values.get(c, 0.0) for c in feature_cols_cure], dtype=float)
    np.nan_to_num(cure_features, copy=False)
    p_cure = model_cure["booster"].predict(cure_features.reshape(1, -1))[0]

    if model_payment:
        feature_cols_pay = model_payment["feature_cols"]
        pay_features = np.array([feature_values.get(c, 0.0) for c in feature_cols_pay], dtype=float)
        np.nan_to_num(pay_features, copy=False)
        p_payment = model_payment["booster"].predict(pay_features.reshape(1, -1))[0]
    else:
        p_payment = 1.0 - p_cure

    gate_results = evaluate(case_row, as_of_ts)
    allowed = [a for a, r in gate_results.items() if r.allowed]
    blocked = [a for a, r in gate_results.items() if not r.allowed]
    blocked_reasons = {a: r.reasons for a, r in gate_results.items() if not r.allowed}

    expected_amount = feature_values.get("total_past_due", feature_values.get("total_overdue", 1000.0))
    ranked = rank_actions(case_row, p_cure, p_payment, expected_amount, allowed)
    best_action = ranked[0][0] if ranked else "do_nothing"
    best_score = ranked[0][1] if ranked else 0.0

    try:
        reasons = get_shap_reasons(model_cure, cure_features, feature_values,
                                   top_n=3, include_counterfactual=True)
    except Exception:
        reasons = ["Model prediction based on case features",
                    "Contact and payment history considered",
                    "Bureau and delinquency data analysed"]

    human_review, review_reason = needs_human_review(case_row)

    time_window = "17:00-19:00 local" if best_action == "call" else "next business day"

    return {
        "case_id": case_row.get("case_id"),
        "golden_id": case_row.get("golden_id"),
        "as_of_ts": as_of_ts or dt.datetime.now(),
        "action": best_action,
        "channel": best_action if best_action in ("call", "sms", "email") else None,
        "time_window": time_window,
        "score": round(float(best_score), 4),
        "reason_1": reasons[0] if len(reasons) > 0 else None,
        "reason_2": reasons[1] if len(reasons) > 1 else None,
        "reason_3": reasons[2] if len(reasons) > 2 else None,
        "blocked_actions": ", ".join(blocked) if blocked else None,
        "hardship_flag": case_row.get("hardship_flag", False),
        "needs_human_review": human_review,
        "model_version": MODEL_VERSION,
        "p_cure_30d": round(float(p_cure), 4),
        "p_payment_7d": round(float(p_payment), 4),
    }


def build_recommendations(con, as_of_ts: dt.datetime | None = None) -> int:
    """Score all open cases and write gold.nba_recommendation."""
    from ontrack.l3_features.structured.features import build_case_features
    from ontrack.l4_nba.models import load_model

    build_case_features(con, config.SNAPSHOT_DATE)

    try:
        model_cure = load_model("self_cure_30d")
    except FileNotFoundError:
        print("WARNING: self_cure_30d model not found. Train models first.")
        return 0

    try:
        model_payment = load_model("payment_7d")
    except FileNotFoundError:
        model_payment = None
        print("WARNING: payment_7d model not found, using fallback.")

    features_df = con.execute("""
        SELECT f.*, cs.hardship_flag, cs.complaint_flag,
               cu.consent_call, cu.consent_sms, cu.consent_email,
               cu.consent_push, cu.consent_autodialer,
               cu.internal_do_not_call_flag, cu.cease_communication_flag,
               cu.insolvency_flag, cu.deceased_flag, cu.third_party_hold_flag,
               cu.vulnerability_flag, cu.preferred_language
        FROM features.case_features f
        JOIN gold.case_360 cs ON cs.case_id = f.case_id
        LEFT JOIN gold.c360_customer cu ON cu.golden_id = f.golden_id
        WHERE cs.outcome IS NULL
    """).fetchdf()

    feature_cols = model_cure["feature_cols"]
    recommendations = []

    for _, row in features_df.iterrows():
        row_dict = row.to_dict()
        feature_values = {c: float(row_dict.get(c, 0) or 0) for c in feature_cols}
        features_array = np.array([feature_values.get(c, 0.0) for c in feature_cols], dtype=float)

        rec = recommend_for_case(
            case_row=row_dict,
            features_row=features_array,
            feature_values=feature_values,
            model_cure=model_cure,
            model_payment=model_payment,
            as_of_ts=as_of_ts,
        )
        recommendations.append(rec)

    if not recommendations:
        print("No open cases to recommend for.")
        return 0

    import pandas as pd
    rec_df = pd.DataFrame(recommendations)

    con.execute("CREATE OR REPLACE TABLE gold.nba_recommendation AS SELECT * FROM rec_df")

    n = con.execute("SELECT count(*) FROM gold.nba_recommendation").fetchone()[0]
    print(f"\ngold.nba_recommendation  {n:>12,d} rows", flush=True)

    print("\n--- Sample recommendations (5) ---")
    sample = con.execute("""
        SELECT case_id, action, score, reason_1, reason_2, reason_3,
               blocked_actions, hardship_flag, needs_human_review
        FROM gold.nba_recommendation
        ORDER BY score DESC
        LIMIT 5
    """).fetchdf()
    print(sample.to_string(index=False))

    return n


def create_decision_log(con) -> None:
    """Create the l4.decision_log table."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS l4.decision_log (
            decision_id VARCHAR PRIMARY KEY,
            case_id VARCHAR,
            agent_id VARCHAR,
            recommended_action VARCHAR,
            agent_action VARCHAR,
            final_action VARCHAR,
            reason_code VARCHAR,
            note VARCHAR,
            ts TIMESTAMP DEFAULT now()
        )
    """)


def record_decision(
    con,
    case_id: str,
    agent_id: str,
    recommended_action: str,
    agent_action: str,
    final_action: str,
    reason_code: str = "",
    note: str = "",
) -> str:
    """Record an agent's accept/edit/reject decision."""
    decision_id = str(uuid.uuid4())
    con.execute("""
        INSERT INTO l4.decision_log
        (decision_id, case_id, agent_id, recommended_action, agent_action,
         final_action, reason_code, note, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, now())
    """, [decision_id, case_id, agent_id, recommended_action, agent_action,
          final_action, reason_code, note])
    return decision_id
