"""R5: Ask questions over P3's gold.nba_recommendation (owner: P2).

Design, Layer 2 example: "Which open cases are most likely to roll to a worse bucket in the next 30 days?"
-> open cases in gold.case_360 joined to gold.nba_recommendation, ranked by risk, with the top reasons per case.

Wired into ask.Engine.answer: roll-forward questions are answered from the same scores the agent sees
(design: "Layer 2 answers it from the same numbers the agent sees"). `python -m ontrack.l2_ask.nba_questions`
checks the table and prints the answer.
"""
from __future__ import annotations

import sys

INTERFACE = ["case_id", "golden_id", "as_of_ts", "action", "channel", "time_window", "score", "reason_1",
             "reason_2", "reason_3", "blocked_actions", "hardship_flag", "needs_human_review", "model_version"]
RISK_CANDIDATES = ["p_roll_forward", "roll_forward_prob", "roll_forward_score", "p_roll", "score"]


def status(con) -> tuple[bool, list[str], str | None]:
    cols = [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'gold' "
        "AND table_name = 'nba_recommendation'").fetchall()]
    missing = [c for c in INTERFACE if c not in cols]
    risk = next((c for c in RISK_CANDIDATES if c in cols), None)
    return bool(cols) and not missing, missing if cols else INTERFACE, risk


def rollforward_sql(risk_col: str, limit: int = 20) -> str:
    return (f"SELECT r.case_id, c.current_bucket, c.current_dpd, round(r.{risk_col}, 4) AS roll_forward_risk, "
            f"r.action, r.reason_1, r.reason_2, r.reason_3, r.needs_human_review "
            f"FROM gold.nba_recommendation r JOIN gold.case_360 c ON c.case_id = r.case_id "
            f"WHERE c.outcome IS NULL ORDER BY r.{risk_col} DESC, c.current_dpd DESC, r.case_id LIMIT {int(limit)}")


ROLL_FORWARD_RE = (r"(most likely|highest (?:risk|chance|probability)|at (?:most |highest )?risk|riskiest).{0,60}"
                   r"roll|roll(?:ing)?[- ]forward (?:risk|probability)|likely to roll|roll to a worse bucket")


def main() -> int:
    from ontrack.db import connect
    con = connect(read_only=True)
    ok, missing, risk = status(con)
    if not ok:
        print(f"gold.nba_recommendation not ready: missing {missing}")
        return 0
    print(f"ready; risk column: {risk}")
    print(con.execute(rollforward_sql(risk, 10)).df().to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
