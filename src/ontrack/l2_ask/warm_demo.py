"""Warm the Ask cache for the demo video (owner: P2): asks the segment's questions exactly as the Ask page does,
so they answer instantly while recording. (run_benchmark's cache keys include question ids, the page's don't.)

    python -m ontrack.l2_ask.warm_demo
"""
import sys
import time

from ontrack.db import connect
from ontrack.l2_ask import ask

DEMO_QUESTIONS = [
    "What is the average days past due of open cases by queue?",
    "Summarise the most recent recorded call on case CS-2026-583749: what did the customer say and agree to?",
    "How long does the 3-month reduced payment programme last, and what share of the payment is reduced?",
    "Rank customers by citizenship status so newcomers are called first.",
    "What was the right-party contact rate on outbound calls in September 2026, by local hour of day?",
]


def main() -> int:
    eng = ask.Engine(connect(read_only=True))
    for q in DEMO_QUESTIONS:
        t0 = time.time()
        a = eng.answer(q)
        print(f"[{a.route:10s}] {time.time() - t0:5.1f}s  {q[:70]}\n    -> {a.answer.splitlines()[0][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
