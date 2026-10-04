"""19:00 safety net: rewrite a benchmark questions file as clean UTF-8, comma-delimited, trimmed headers, unique ids.

    python scripts/normalize_questions.py <in.csv> <out.csv> [--append-released <benchmark_questions.csv>]

Handles what K10 found breaks run_benchmark: Windows-1252 (Excel) encoding, spaces in the header, semicolon or tab
delimiters, duplicate question ids (first one kept). With --append-released, the released questions come first, then
the file's questions; an id in both is kept once (released wins), so the output always holds every released question
whatever the organisers' file contains. Prints what it changed. Never edits question text.
"""
import argparse
import csv
import io
import sys
from pathlib import Path


def read_rows(src: str) -> tuple[list[str], list[list[str]]]:
    raw = Path(src).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max(",;	", key=first.count)
    print(f"{Path(src).name}: encoding {enc}, delimiter {delim!r}")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    header = [h.strip().lower() for h in rows[0]]
    if "question_id" not in header or "question_text" not in header:
        raise SystemExit(f"ERROR: header {header} has no question_id / question_text")
    return header, [dict(zip(header, (r + [""] * len(header))[:len(header)])) for r in rows[1:]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Clean a benchmark questions file")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--append-released", help="released benchmark_questions.csv; its questions come first")
    args = ap.parse_args(argv)
    header, rows = read_rows(args.src)
    n_file = len(rows)
    if args.append_released:
        rel_header, released = read_rows(args.append_released)
        header = rel_header + [h for h in header if h not in rel_header]
        rows = released + rows
    seen, out, dups = set(), [], []
    for r in rows:
        qid = r.get("question_id", "").strip()
        if qid in seen:
            dups.append(qid)
            continue
        seen.add(qid)
        out.append([qid if h == "question_id" else r.get(h, "") for h in header])
    with open(args.dst, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out)
    print(f"{len(out)} questions written to {args.dst} ({n_file} in {Path(args.src).name}"
          + (f", released file appended first" if args.append_released else "") + f"); duplicate ids dropped: {len(dups)}" + (f" ({', '.join(dups[:5])}{', ...' if len(dups) > 5 else ''})" if dups else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
