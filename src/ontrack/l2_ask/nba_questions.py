"""R5 / G5: Ask questions over P3's gold.nba_recommendation (owner: P2).

Design, Layer 2 example: "Which open cases are most likely to roll to a worse bucket in the next 30 days?"
-> open cases in gold.case_360 joined to gold.nba_recommendation, ranked by risk, with the top reasons per case.

Two risk lists (agreed with P3 on #13 / #16):
  * p_roll_forward    : DPD <= 150; a case can still roll to a worse bucket;
  * p_charge_off_risk : DPD 151-180; the next step is charge-off at 181, so "roll forward" would mislead.
Each list sorts NULLS LAST and filters its own rows, so the two never mix.

Wired into ask.Engine.answer: both are answered from the same scores the agent sees (design: "Layer 2 answers it
from the same numbers the agent sees"). `python -m ontrack.l2_ask.nba_questions` checks the table and prints both.
"""
from __future__ import annotations

import sys

INTERFACE = ["case_id", "golden_id", "as_of_ts", "action", "channel", "time_window", "score", "reason_1",
             "reason_2", "reason_3", "blocked_actions", "hardship_flag", "needs_human_review", "model_version"]
RISK_CANDIDATES = ["p_roll_forward", "roll_forward_prob", "roll_forward_score", "p_roll", "score"]
CHARGE_OFF_COL = "p_charge_off_risk"

ROLL_FORWARD_RE = (r"(most likely|highest (?:risk|chance|probability)|at (?:most |highest )?risk|riskiest).{0,60}"
                   r"roll|roll(?:ing)?[- ]forward (?:risk|probability)|likely to roll|roll to a worse bucket")
CHARGE_OFF_RE = (r"(closest|nearest|most likely|highest (?:risk|chance|probability)|at (?:most |highest )?risk).{0,40}"
                 r"(charge[- ]?off|charged[- ]?off|write[- ]?off|written[- ]?off)|charge[- ]?off risk")


def columns(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'gold' "
        "AND table_name = 'nba_recommendation'").fetchall()]


def status(con) -> tuple[bool, list[str], str | None]:
    cols = columns(con)
    missing = [c for c in INTERFACE if c not in cols]
    risk = next((c for c in RISK_CANDIDATES if c in cols), None)
    return bool(cols) and not missing, missing if cols else INTERFACE, risk


def _ranked_sql(risk_col: str, label: str, limit: int, cols: list[str]) -> str:
    # Calibrated probabilities are steps (~24K cases tie at p ≈ 1.0), so the second key decides the top of the list:
    # P3's model_risk_rank (1 = most likely to stay unpaid, from the raw score; agreed on #13), else dollars at stake.
    overdue = "r.overdue_now" if "overdue_now" in cols else "c.total_overdue"
    tie = "r.model_risk_rank ASC" if "model_risk_rank" in cols else f"{overdue} DESC NULLS LAST"
    rank = ", r.model_risk_rank" if "model_risk_rank" in cols else ""
    return (f"SELECT r.case_id, c.current_bucket, c.current_dpd, round({overdue}, 2) AS overdue_cad, "
            f"round(r.{risk_col}, 4) AS {label}{rank}, r.action, r.reason_1, r.reason_2, r.reason_3, "
            f"r.needs_human_review FROM gold.nba_recommendation r JOIN gold.case_360 c ON c.case_id = r.case_id "
            f"WHERE c.outcome IS NULL AND r.{risk_col} IS NOT NULL "
            f"ORDER BY r.{risk_col} DESC NULLS LAST, {tie}, r.case_id LIMIT {int(limit)}")


def rollforward_sql(risk_col: str, limit: int = 20, cols: list[str] | None = None) -> str:
    return _ranked_sql(risk_col, "roll_forward_risk", limit, cols or [])


def chargeoff_sql(limit: int = 20, cols: list[str] | None = None) -> str:
    return _ranked_sql(CHARGE_OFF_COL, "charge_off_risk", limit, cols or [])


def main() -> int:
    from ontrack.db import connect
    con = connect(read_only=True)
    ok, missing, risk = status(con)
    if not ok:
        print(f"gold.nba_recommendation not ready: missing {missing}")
        return 0
    print(f"ready; roll-forward column: {risk}; charge-off column: "
          f"{CHARGE_OFF_COL if CHARGE_OFF_COL in columns(con) else 'missing'}")
    cols = columns(con)
    print(con.execute(rollforward_sql(risk, 5, cols)).df().to_string(index=False))
    if CHARGE_OFF_COL in cols:
        print(con.execute(chargeoff_sql(5, cols)).df().to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
