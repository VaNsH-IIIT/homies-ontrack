"""Pre-submission check (owner: P1). Run before submitting; judges can run it too.

    python scripts/check_submission.py                       # repo checks only (no data needed)
    python scripts/check_submission.py --questions <csv>     # also: one answer row per question id in <csv>

Checks: every deliverable file exists; every relative link in README.md resolves; benchmark/answers.csv has the
template columns, unique ids, refused true/false, no empty answers; the data contract YAML parses; no secrets or
data files are tracked by git. Exit 0 when everything passes.
"""
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DELIVERABLES = {
    "Architecture diagram (PDF)": "docs/architecture/architecture.pdf",
    "Architecture diagram (PNG)": "docs/architecture/architecture.png",
    "Data contract": "contracts/c360_customer.yaml",
    "Data quality report": "docs/data_quality_report.md",
    "Benchmark answers": "benchmark/answers.csv",
    "Pitch deck (PDF)": "docs/pitch/OnTrack_pitch_deck.pdf",
    "AI tools used": "AI_TOOLS.md",
    "README": "README.md",
}
ANSWER_COLUMNS = ["question_id", "answer", "sql_or_sources", "refused"]
TRACKED_FORBIDDEN = re.compile(r"(^|/)\.env$|\.(duckdb|parquet|zip|pkl|joblib)$|^data/")


def readme_links(text: str) -> list[str]:
    """Relative link targets in markdown links, without anchors; external and pure-anchor links skipped."""
    out = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        out.append(target.split("#", 1)[0])
    return out


def check_answers(path: Path, question_ids: list[str] | None = None) -> list[str]:
    """Problems with an answers file in the benchmark template format; empty list when it is valid."""
    problems = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ANSWER_COLUMNS:
            problems.append(f"columns {reader.fieldnames} != template {ANSWER_COLUMNS}")
            return problems
        rows = list(reader)
    ids = [r["question_id"] for r in rows]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        problems.append(f"duplicate question ids: {dups}")
    bad_refused = [r["question_id"] for r in rows if r["refused"].strip().lower() not in ("true", "false")]
    if bad_refused:
        problems.append(f"refused is not true/false for {bad_refused}")
    empty = [r["question_id"] for r in rows if not r["answer"].strip()]
    if empty:
        problems.append(f"empty answers for {empty}")
    not_answered = [r["question_id"] for r in rows if r["answer"].startswith("Not answered")]
    if not_answered:
        problems.append(f"'Not answered' rows (no LLM or a failure) for {not_answered}")
    if question_ids is not None:
        missing = [q for q in question_ids if q not in set(ids)]
        extra = [i for i in ids if i not in set(question_ids)]
        if missing:
            problems.append(f"questions without an answer row: {missing}")
        if extra:
            problems.append(f"answer rows for unknown question ids: {extra}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-submission check")
    ap.add_argument("--questions", help="the questions file the answers must cover (any shape run_benchmark reads)")
    args = ap.parse_args(argv)
    results = []

    for name, rel in DELIVERABLES.items():
        p = REPO / rel
        results.append((f"{name}: {rel}", p.exists() and p.stat().st_size > 0))

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    broken = [t for t in readme_links(readme) if not (REPO / t).exists()]
    results.append((f"README links resolve ({len(readme_links(readme))} relative links)"
                    + (f"; broken: {broken}" if broken else ""), not broken))

    qids = None
    if args.questions:
        with open(args.questions, encoding="utf-8-sig", errors="replace", newline="") as f:
            qids = [r[0].strip() for r in list(csv.reader(f))[1:] if r and r[0].strip()]
    problems = check_answers(REPO / "benchmark" / "answers.csv", qids)
    results.append(("benchmark/answers.csv matches the template" + (f": {'; '.join(problems)}" if problems else ""),
                    not problems))

    try:
        contract = yaml.safe_load((REPO / "contracts" / "c360_customer.yaml").read_text(encoding="utf-8"))
        results.append(("data contract YAML parses", isinstance(contract, dict)))
    except yaml.YAMLError as e:
        results.append((f"data contract YAML parses: {e}", False))

    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout.splitlines()
    leaked = [t for t in tracked if TRACKED_FORBIDDEN.search(t)]
    results.append(("no secrets or data files tracked by git" + (f": {leaked}" if leaked else ""), not leaked))

    for label, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label}")
    failed = sum(not ok for _, ok in results)
    print(f"\n{len(results) - failed}/{len(results)} checks pass")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
