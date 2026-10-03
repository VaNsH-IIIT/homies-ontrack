"""Score an answers file against the dev gold answers (owner: P2).

    python -m ontrack.l2_ask.score_dev                        # benchmark/answers.csv vs labels/benchmark_dev_answers.csv
    python -m ontrack.l2_ask.score_dev --answers other.csv -v # show every miss

Our approximation of the organisers' automatic scoring (release README):
  * refusals: gold "Refuse: ..." must have refused = true; every other question must have refused = false;
  * tables / numbers: gold rows matched to ours by key, every gold number within the question's tolerance;
  * documents / transcripts: the cited document (or transcript) and most key facts (numbers, key terms) present.
Prints answer accuracy, refusal accuracy and the worst failure types.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

from ontrack import config

STOP = set("a an the and or of to in on for by with is are be was were it its at as from that this than then "
           "before after any into per their they them customer agent should must can".split())


def parse_tolerance(tol: str) -> tuple[float, float]:
    """(tolerance for rates/amounts, tolerance for counts). 'exact' -> 0."""
    tol = (tol or "").lower()
    nums = [float(x) for x in re.findall(r"±\s*([\d.]+)", tol)]
    main = nums[-1] if nums else 0.0
    return main, 0.0 if "exact" in tol or "count" in tol else main


def to_num(s: str):
    s = str(s).strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def parse_table(text: str) -> tuple[list[str], list[list[str]]] | None:
    text = (text or "").strip()
    if not text or ("," not in text and ":" not in text):
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if all(":" in ln and "," not in ln for ln in lines):            # key: value per line
        rows = [[p.strip() for p in ln.split(":", 1)] for ln in lines]
        return ["key", "value"], rows
    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    if len(rows) < 2:
        return None
    return [h.strip().lower() for h in rows[0]], [r for r in rows[1:] if r]


def score_table(gold: str, ours: str, tol: str) -> tuple[bool, str]:
    g, o = parse_table(gold), parse_table(ours)
    if not g:
        return False, "gold not a table"
    if not o:
        return False, "answer not a table"
    gh, grows = g
    oh, orows = o
    rate_tol, count_tol = parse_tolerance(tol)
    single = len(grows) == 1 and all(to_num(x) is not None for x in grows[0])
    if single:                                # one row of numbers: compare the first number found
        want = to_num(grows[0][0])
        got = next((to_num(x) for r in orows for x in r if to_num(x) is not None), None)
        if got is None:
            return False, "no number in answer"
        return abs(got - want) <= rate_tol + 1e-9, f"want {want}, got {got}"
    okey = {norm_key(r[0]): r for r in orows}
    for gr in grows:
        r = okey.get(norm_key(gr[0]))
        if r is None:
            return False, f"missing row {gr[0]!r}"
        for j, (name, gv) in enumerate(zip(gh[1:], gr[1:]), start=1):
            want = to_num(gv)
            if want is None:
                continue
            k = oh.index(name) if name in oh else j
            got = to_num(r[k]) if k < len(r) else None
            is_count = float(want).is_integer() and abs(want) >= 20 and j > 1
            t = count_tol if is_count else rate_tol
            if got is None or abs(got - want) > t + 1e-9:
                return False, f"row {gr[0]!r} col {name}: want {want}, got {got}"
    return True, ""


def key_terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9$%.]+", text.lower())
    return {w.strip(".") for w in words if w not in STOP and len(w.strip(".")) > 2 or re.match(r"\$?\d", w)}


def score_document(gold: str, gold_sources: str, ours: str, our_sources: str) -> tuple[bool, str]:
    try:
        wanted = json.loads(gold_sources) if gold_sources else []
    except json.JSONDecodeError:
        wanted = [gold_sources]
    cited = our_sources + " " + ours
    docs = {re.split(r"[\s§]", w)[0] + ("" if not w.startswith("transcript") else " " + w.split()[-1]) for w in wanted}
    hit = [d for d in docs if d.lower() in cited.lower()]
    if wanted and not hit:
        return False, f"cites none of {sorted(docs)}"
    g, o = key_terms(gold), key_terms(ours)
    nums = {w for w in g if re.match(r"\$?\d", w)}
    if nums - o:
        return False, f"missing numbers {sorted(nums - o)}"
    cover = len(g & o) / max(1, len(g))
    return cover >= 0.4, f"key-term coverage {cover:.0%}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score answers against dev gold")
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "benchmark" / "answers.csv"))
    ap.add_argument("--gold", default=str(config.DATA_DIR / "labels" / "benchmark_dev_answers.csv"))
    ap.add_argument("--questions", default=str(config.DATA_DIR / "data" / "benchmark_questions.csv"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    read = lambda p: {r["question_id"]: r for r in csv.DictReader(open(p, encoding="utf-8-sig", newline=""))}
    gold, ans, qs = read(args.gold), read(args.answers), read(args.questions)

    results, failures = [], Counter()
    for qid, g in gold.items():
        a = ans.get(qid, {"answer": "", "sql_or_sources": "", "refused": "false"})
        refused = str(a.get("refused", "")).strip().lower() == "true"
        should_refuse = g["gold_answer"].strip().lower().startswith("refuse")
        if should_refuse or refused:
            ok = refused == should_refuse
            kind = "refusal" if should_refuse else "data/doc"
            why = "" if ok else ("not refused" if should_refuse else "wrongly refused")
        elif g["gold_sql_reference"].strip():
            kind = "data"
            ok, why = score_table(g["gold_answer"], a["answer"], qs.get(qid, {}).get("tolerance", ""))
        else:
            kind = "transcript" if "transcript" in g["gold_sources"] else "document"
            ok, why = score_document(g["gold_answer"], g["gold_sources"], a["answer"], a["sql_or_sources"])
            why = "" if ok else why
        results.append((qid, kind, should_refuse, ok, why))
        if not ok:
            failures[f"{kind}: {re.sub(r'[0-9.]+|' + chr(39) + '.*?' + chr(39), '#', why)[:60]}"] += 1

    n = len(results)
    correct = sum(r[3] for r in results)
    ref = [r for r in results if r[2]]
    non_ref = [r for r in results if not r[2]]
    print(f"Dev answer accuracy : {correct}/{n} = {100 * correct / max(1, n):.1f}%")
    print(f"Refusal accuracy    : {sum(r[3] for r in ref)}/{len(ref)} should-refuse refused; "
          f"{sum(1 for r in non_ref if not (r[4] == 'wrongly refused'))}/{len(non_ref)} others not refused")
    by_kind = Counter(r[1] for r in results)
    for kind in sorted(by_kind):
        ok = sum(1 for r in results if r[1] == kind and r[3])
        print(f"  {kind:10s} {ok}/{by_kind[kind]}")
    print("Worst failure types:")
    for k, c in failures.most_common(3):
        print(f"  {c} x {k}")
    if args.verbose:
        for qid, kind, _, ok, why in results:
            print(f"  {'OK  ' if ok else 'MISS'} {qid} {kind:10s} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
