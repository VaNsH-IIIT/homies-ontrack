"""Answer a whole benchmark question file in one command (owner: P2).

    python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv
    python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv --only BQ-004,BQ-035
    python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv --retry-failed --workers 2

Always writes one row per question, in question order, in the template format
(question_id, answer, sql_or_sources, refused). A question that fails still gets a row, so the file is
never short; the error goes to the log, not into the answer. No hand edits: answers come from ask.answer().
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ontrack import config
from ontrack.db import connect
from ontrack.l2_ask import ask, llm

FIELDS = ["question_id", "answer", "sql_or_sources", "refused"]
trace_lock = threading.Lock()
FAILED_PREFIXES = ("Could not answer", "Not answered", "Could not run")


def read_questions(path: Path) -> list[dict]:
    """Read a questions file in whatever shape it arrives (G10): UTF-8 with or without BOM, or Windows-1252 (Excel's
    plain CSV save); comma, semicolon or tab delimited; CRLF; header names with spaces or capitals; any column order,
    extra or missing optional columns; blank lines. Duplicate ids are answered once (first wins, with a warning)."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    text = text.lstrip("﻿")
    header = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max([",", ";", "\t", "|"], key=header.count) if header else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    rows_raw = [r for r in reader if any(c.strip() for c in r)]
    if not rows_raw:
        raise SystemExit(f"{path}: no rows")
    names = [re.sub(r"\s+", "_", h.strip().lstrip("﻿").lower()) for h in rows_raw[0]]
    if "question_id" not in names or "question_text" not in names:
        raise SystemExit(f"{path}: expected columns question_id, question_text (found {names})")
    rows, seen = [], set()
    for r in rows_raw[1:]:
        rec = {n: (r[i].strip() if i < len(r) else "") for i, n in enumerate(names)}
        qid = rec["question_id"]
        if not qid:
            continue
        if not rec["question_text"]:                 # keep the id: every id the organisers send gets a row
            print(f"  WARNING: question_id {qid} has no question text: written as 'Not answered'", flush=True)
        if qid in seen:
            print(f"  WARNING: duplicate question_id {qid}: answered once (first occurrence kept)", flush=True)
            continue
        seen.add(qid)
        rows.append(rec)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Answer benchmark questions")
    ap.add_argument("--questions", default=str(config.DATA_DIR / "data" / "benchmark_questions.csv"))
    ap.add_argument("--out", default=str(config.REPO_ROOT / "benchmark" / "answers.csv"))
    ap.add_argument("--only", default="", help="comma-separated question_ids to run (others are kept from --out)")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached LLM responses")
    ap.add_argument("--workers", type=int, default=4, help="questions answered in parallel")
    ap.add_argument("--retries", type=int, default=1, help="extra attempts for a question that errors")
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-run only the questions that failed or are missing in --out; keep the others")
    args = ap.parse_args(argv)

    questions = read_questions(Path(args.questions))
    only = {q.strip() for q in args.only.split(",") if q.strip()}
    out = Path(args.out)
    previous = {}
    if (only or args.retry_failed) and out.exists():
        with open(out, encoding="utf-8", newline="") as f:
            previous = {r["question_id"]: r for r in csv.DictReader(f)}
    if args.retry_failed:                   # re-run only questions that errored (or are missing) in --out
        only = {q["question_id"] for q in questions
                if q["question_id"] not in previous
                or previous[q["question_id"]]["answer"].startswith(FAILED_PREFIXES)}
        print(f"Retrying {len(only)} failed or missing question(s): {', '.join(sorted(only)) or '-'}", flush=True)
        if not only:
            return 0

    con = connect(read_only=True)
    engine = ask.Engine(con, use_cache=not args.no_cache)
    if llm.available():
        _ = engine.context                                   # build the shared prompt once, before the threads
    start = time.time()
    trace_path = config.WORK_DIR / "benchmark_trace.jsonl"

    def one(q: dict) -> tuple[dict, str]:
        qid = q["question_id"]
        t0 = time.time()
        a = None
        if not q.get("question_text"):
            a = ask.Answer(answer="Not answered: the question text is empty", sql_or_sources="", refused=False,
                           route="error")
        for attempt in range(0 if a else 1 + args.retries):   # an LLM hiccup must not cost a question
            try:
                a = engine.answer(q["question_text"], as_of_date=q.get("as_of_date") or config.SNAPSHOT_DATE,
                                  metric_id=q.get("metric_id") or None, question_id=qid,
                                  tolerance=q.get("tolerance") or "")
            except Exception as e:  # noqa: BLE001 - never lose a row
                print(f"  {qid}: attempt {attempt + 1} ERROR {type(e).__name__}: {str(e)[:200]}", file=sys.stderr,
                      flush=True)
                a = ask.Answer(answer="Could not answer: internal error", sql_or_sources="", refused=False,
                               route="error")
            if a.route != "error":
                break
        row = {"question_id": qid, "answer": a.answer, "sql_or_sources": a.sql_or_sources,
               "refused": "true" if a.refused else "false"}
        with trace_lock, open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"question_id": qid, "question": q["question_text"], "route": a.route,
                                "seconds": round(time.time() - t0, 1), "understood_as": a.understood_as,
                                **row}, ensure_ascii=False, default=str) + "\n")
        first = (a.answer.splitlines() or [""])[0][:70]
        return row, f"  {qid} [{a.route:8s}] {time.time() - t0:5.1f}s  {first}"

    todo = [q for q in questions if not (only and q["question_id"] not in only and q["question_id"] in previous)]
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(one, q): q["question_id"] for q in todo}
        for f in as_completed(futs):
            row, line = f.result()
            results[row["question_id"]] = row
            print(line, flush=True)
    rows = [results.get(q["question_id"]) or previous[q["question_id"]] for q in questions]
    failed = sum(1 for r in rows if r["answer"].startswith(FAILED_PREFIXES))

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL, lineterminator="\n")  # as the template
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} answers to {out} in {time.time() - start:.0f}s ({failed} errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
