"""19:00 safety net: rewrite a benchmark questions file as clean UTF-8, comma-delimited, trimmed headers, unique ids.

    python normalize_questions.py <in.csv> <out.csv>

Handles what K10 found breaks run_benchmark: Windows-1252 (Excel) encoding, spaces in the header, semicolon or tab
delimiters, duplicate question ids (first one kept). Prints what it changed. Never edits question text.
"""
import csv
import io
import sys
from pathlib import Path


def main(src: str, dst: str) -> int:
    raw = Path(src).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    print(f"encoding: {enc}")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max(",;\t", key=first.count)
    print(f"delimiter: {delim!r}")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    header = [h.strip().lower() for h in rows[0]]
    if "question_id" not in header or "question_text" not in header:
        print(f"ERROR: header {header} has no question_id / question_text")
        return 1
    qi = header.index("question_id")
    seen, out, dups = set(), [], []
    for r in rows[1:]:
        r = (r + [""] * len(header))[:len(header)]
        r[qi] = r[qi].strip()
        if r[qi] in seen:
            dups.append(r[qi])
            continue
        seen.add(r[qi])
        out.append(r)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out)
    print(f"{len(out)} questions written to {dst}; duplicate ids dropped: {dups or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
