"""Backup runner for the 19:00 benchmark (owner: P2, G13). One command on any teammate's machine.

    python -m ontrack.l2_ask.backup_run --questions <organisers' file>          # answers to $WORK_DIR/outputs (scratch)

The released 35 are always kept: the organisers' file is merged after them (ids once, released first), and the
output is checked to contain every released id. Only after check_submission passes is the scratch file copied to
benchmark/answers.csv.

Steps (each one prints OK or what to fix):
  1. preflight: data folder, database with bronze + gold tables, search index (built if missing), LLM access
     (API key or a logged-in Claude Code CLI; one tiny test call), questions file readable (any shape, see G10);
  2. run_benchmark with --workers N;
  3. up to --rounds re-runs of only the failed questions (--retry-failed), fewer workers each round;
  4. validate: one row per unique question id, no failed rows, refused is true/false, template columns;
  5. print the git steps (main is protected: commit on a branch and open a PR; never edit answers.csv by hand).
Exit code 0 only when the file is complete.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from ontrack import config

FAILED = ("Could not answer", "Not answered", "Could not run")


def step(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


def preflight(questions: Path, check_llm: bool) -> bool:
    from ontrack.db import DB_PATH, connect
    from ontrack.l2_ask import llm, run_benchmark, search
    ok = True
    step("1/5 preflight")
    print(f"  data folder: {config.DATA_DIR} {'OK' if config.DATA_DIR.exists() else 'MISSING: set MAPLE_DATA_DIR in .env'}")
    ok &= config.DATA_DIR.exists()
    if not DB_PATH.exists():
        print(f"  database: MISSING {DB_PATH}: run `python -m ontrack.l1_factory.bronze` then "
              f"`python -m ontrack.l1_factory.build`")
        return False
    con = connect(read_only=True)
    need = {"bronze": ["collections_cases", "contact_history", "promises_to_pay", "call_transcripts"],
            "gold": ["c360_customer", "case_360"]}
    for schema, tables in need.items():
        have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
                                          [schema]).fetchall()}
        missing = [t for t in tables if t not in have]
        print(f"  {schema} tables: {'OK' if not missing else 'MISSING ' + ', '.join(missing)}")
        ok &= not missing
    con.close()
    if not search.INDEX_PATH.exists():
        print("  search index: missing, building (about 1 min)…", flush=True)
        search.build()
    print("  search index: OK")
    backend = llm.backend()
    print(f"  LLM backend: {backend or 'NONE: set ANTHROPIC_API_KEY or log in to Claude Code (`claude`)'}"
          f" · model {llm.MODEL}")
    ok &= backend is not None
    if backend and check_llm:
        try:
            t0 = time.time()
            r = llm.complete_json("Reply with JSON.", "Say ok.", {"type": "object", "properties": {
                "ok": {"type": "boolean"}}, "required": ["ok"]}, timeout=180)
            print(f"  LLM test call: OK ({time.time() - t0:.0f} s, {r})")
        except Exception as e:  # noqa: BLE001
            print(f"  LLM test call: FAILED {type(e).__name__}: {str(e)[:200]}")
            print("    -> usage limit? wait for the reset, use another account, or set ANTHROPIC_API_KEY in .env")
            ok = False
    try:
        qs = run_benchmark.read_questions(questions)
        print(f"  questions: {len(qs)} unique ids from {questions}")
    except SystemExit as e:
        print(f"  questions: UNREADABLE {e}")
        ok = False
    return ok


def released_ids(released: Path | None = None) -> list[str]:
    """The released benchmark ids (BQ-001 … BQ-035) from $MAPLE_DATA_DIR, or [] if the file isn't there."""
    from ontrack.l2_ask import run_benchmark
    path = released or config.DATA_DIR / "data" / "benchmark_questions.csv"
    return [q["question_id"] for q in run_benchmark.read_questions(path)] if Path(path).exists() else []


def merge_with_released(questions: Path, released: Path, dest: Path) -> tuple[int, int]:
    """Released questions first, then the file's questions; an id in both is kept once (released wins), so the
    answers can never lose BQ-001 … BQ-035 whatever the organisers' file contains (K22 / G17)."""
    from ontrack.l2_ask import run_benchmark
    rel = run_benchmark.read_questions(released)
    extra = run_benchmark.read_questions(questions)
    have = {q["question_id"] for q in rel}
    new = [q for q in extra if q["question_id"] not in have]
    cols = ["question_id", "question_text", "difficulty", "metric_id", "as_of_date", "tolerance", "split"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for q in rel + new:
            w.writerow({c: q.get(c, "") for c in cols})
    return len(rel), len(new)


def validate(questions: Path, out: Path, required: list[str] | None = None) -> list[str]:
    from ontrack.l2_ask import run_benchmark
    qs = run_benchmark.read_questions(questions)
    ids = [q["question_id"] for q in qs]
    blank = {q["question_id"] for q in qs if not q.get("question_text")}   # G10 writes these as "Not answered"
    with open(out, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        rows = list(reader)
    problems = []
    if cols != run_benchmark.FIELDS:
        problems.append(f"columns {cols} != {run_benchmark.FIELDS}")
    got = [r["question_id"] for r in rows]
    if got != ids:
        problems.append(f"ids differ: missing {sorted(set(ids) - set(got))}, extra {sorted(set(got) - set(ids))}, "
                        f"duplicates {sorted({i for i in got if got.count(i) > 1})}")
    failed = [r["question_id"] for r in rows if r["question_id"] not in blank
              and (r["answer"].startswith(FAILED) or not r["answer"].strip())]
    if blank:
        print(f"  WARNING: {len(blank)} question(s) with no text, answered 'Not answered' as expected: "
              f"{sorted(blank)}")
    if failed:
        problems.append(f"failed or empty answers: {failed}")
    missing_released = [i for i in (required if required is not None else released_ids()) if i not in set(got)]
    if missing_released:
        problems.append(f"released questions missing from the answers ({len(missing_released)}): "
                        f"{missing_released[:5]}{' …' if len(missing_released) > 5 else ''}")
    bad_ref = [r["question_id"] for r in rows if r["refused"] not in ("true", "false")]
    if bad_ref:
        problems.append(f"refused not true/false: {bad_ref}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Backup runner for the 19:00 benchmark")
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", default=str(config.WORK_DIR / "outputs" / "answers.csv"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=3, help="retry rounds for failed questions")
    ap.add_argument("--skip-llm-check", action="store_true")
    ap.add_argument("--released", default=str(config.DATA_DIR / "data" / "benchmark_questions.csv"),
                    help="released questions, always kept in the answers (default: $MAPLE_DATA_DIR/data/...)")
    ap.add_argument("--no-append-released", action="store_true",
                    help="use --questions as is (only when it already is the full released + extra file)")
    args = ap.parse_args(argv)
    questions, out = Path(args.questions), Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if not args.no_append_released and Path(args.released).exists():
        final = out.parent / "final_questions.csv"
        n_rel, n_new = merge_with_released(questions, Path(args.released), final)
        print(f"Questions: {n_rel} released + {n_new} new from {questions.name} = {n_rel + n_new} -> {final}")
        questions = final

    if not preflight(questions, not args.skip_llm_check):
        print("\nPREFLIGHT FAILED: fix the items above, then run again.")
        return 2

    from ontrack.l2_ask import run_benchmark
    step(f"2/5 run_benchmark --workers {args.workers}")
    run_benchmark.main(["--questions", str(questions), "--out", str(out), "--workers", str(args.workers)])

    for r in range(1, args.rounds + 1):
        problems = validate(questions, out)
        if not problems:
            break
        workers = max(1, args.workers // (2 ** r))
        step(f"3/5 retry round {r}: --retry-failed --workers {workers}")
        run_benchmark.main(["--questions", str(questions), "--out", str(out), "--retry-failed",
                            "--workers", str(workers)])

    step("4/5 validate")
    problems = validate(questions, out)
    for p in problems:
        print(f"  PROBLEM: {p}")
    if not problems:
        print(f"  OK: {out} has one valid row per question ({time.time() - t0:.0f} s in total)")

    step("5/5 next steps")
    print("  python -m ontrack.l2_ask.score_dev --answers " + str(out) + "     # dev should still be 21/21")
    print(f"  python scripts/check_submission.py --questions {questions} --answers {out}")
    if out.resolve() != (config.REPO_ROOT / "benchmark" / "answers.csv").resolve():
        print(f"  copy {out} benchmark/answers.csv    # the file exactly as generated; never hand-edit")
    print("  git checkout -b p2/final-answers && git add benchmark/answers.csv && "
          "git commit -m \"Benchmark: final answers\" && git push -u origin p2/final-answers")
    print("  then open the PR and ping Vansh in #13 (main is protected)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
