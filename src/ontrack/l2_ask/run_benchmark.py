"""Answer a whole benchmark question file in one command (owner: P2).

    python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv
    python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv --only BQ-004,BQ-035

Always writes one row per question, in question order, in the template format
(question_id, answer, sql_or_sources, refused). A question that fails still gets a row, so the file is
never short; the error goes to the log, not into the answer. No hand edits: answers come from ask.answer().
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from ontrack import config
from ontrack.db import connect
from ontrack.l2_ask import ask

FIELDS = ["question_id", "answer", "sql_or_sources", "refused"]


def read_questions(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or "question_id" not in rows[0] or "question_text" not in rows[0]:
        raise SystemExit(f"{path}: expected columns question_id, question_text")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Answer benchmark questions")
    ap.add_argument("--questions", default=str(config.DATA_DIR / "data" / "benchmark_questions.csv"))
    ap.add_argument("--out", default=str(config.REPO_ROOT / "benchmark" / "answers.csv"))
    ap.add_argument("--only", default="", help="comma-separated question_ids to run (others are kept from --out)")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached LLM responses")
    args = ap.parse_args(argv)

    questions = read_questions(Path(args.questions))
    only = {q.strip() for q in args.only.split(",") if q.strip()}
    out = Path(args.out)
    previous = {}
    if only and out.exists():
        with open(out, encoding="utf-8", newline="") as f:
            previous = {r["question_id"]: r for r in csv.DictReader(f)}

    con = connect(read_only=True)
    engine = ask.Engine(con, use_cache=not args.no_cache)
    rows, failed = [], 0
    start = time.time()
    for q in questions:
        qid = q["question_id"]
        if only and qid not in only and qid in previous:
            rows.append(previous[qid])
            continue
        t0 = time.time()
        try:
            a = engine.answer(q["question_text"], as_of_date=q.get("as_of_date") or config.SNAPSHOT_DATE,
                              metric_id=q.get("metric_id") or None, question_id=qid,
                              tolerance=q.get("tolerance") or "")
        except Exception as e:  # never lose a row
            failed += 1
            print(f"  {qid}: ERROR {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            a = ask.Answer(answer="Could not answer: internal error", sql_or_sources="", refused=False,
                           route="error")
        rows.append({"question_id": qid, "answer": a.answer, "sql_or_sources": a.sql_or_sources,
                     "refused": "true" if a.refused else "false"})
        first = (a.answer.splitlines() or [""])[0][:70]
        print(f"  {qid} [{a.route:8s}] {time.time() - t0:5.1f}s  {first}", flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} answers to {out} in {time.time() - start:.0f}s ({failed} errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
