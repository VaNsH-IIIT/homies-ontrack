"""Cited search (BM25) over reference documents and agent notes (owner: P2). Layer 2, document answers.

    python -m ontrack.l2_ask.search --build            # once (~2 min): $ONTRACK_WORK_DIR/search.duckdb
    python -m ontrack.l2_ask.search "hardship evidence rule"
    python -m ontrack.l2_ask.search "lost job" --notes --case CS-2026-614370

Index: its own small DuckDB file (DuckDB full-text search, BM25), so the main database stays read-only.
  doc_sections: one row per section of every reference document (doc_id, section, version, current flag);
  notes:        agent notes (redacted; notes with redaction_status = needs_review are excluded, as designed).
Every hit carries its citation: "POL-COLL-004 §4.3" or "note N-0003433 (case CS-...)". Superseded document
versions are indexed but ranked after current ones and labelled, so they can be cited only as out of date.
Design change: BM25 only (no bge-m3 embeddings / LanceDB): the corpus is small and templated, and BM25 needs no
model download on the judges' machines.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys

import duckdb

from ontrack import config

INDEX_PATH = config.WORK_DIR / "search.duckdb"


def _sections(doc: dict) -> list[dict]:
    path = config.DATA_DIR / "files" / doc["file_path"]
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not re.search(r"^##\s+", text, flags=re.M) and re.search(r"^\*\*Q\d+\.", text, flags=re.M):
        text = re.sub(r"^\*\*(Q\d+\.[^*]*)\*\*", lambda m: "## " + m.group(1), text, flags=re.M)  # FAQ: per question
    parts = re.split(r"^##\s+", text, flags=re.M)
    title = re.search(r"^#\s+(.+)$", parts[0], flags=re.M)
    out = []
    if len(parts) == 1:                                 # no sections: the whole document
        body = re.sub(r"^>.*$|^#.*$", "", text, flags=re.M).strip()
        out.append({"section": "", "heading": title.group(1) if title else doc["title"], "text": body})
    for p in parts[1:]:
        heading, _, body = p.partition("\n")
        m = re.match(r"(§[\d.]+|Q\d+|\d+)", heading.strip())
        out.append({"section": m.group(1) if m else heading.strip()[:20], "heading": heading.strip(),
                    "text": body.strip()})
    return out


def build() -> None:
    from ontrack.db import connect
    from ontrack.l2_ask.ask import redact
    INDEX_PATH.unlink(missing_ok=True)
    idx = duckdb.connect(str(INDEX_PATH))
    idx.execute("INSTALL fts; LOAD fts")
    rows = []
    with open(config.DATA_DIR / "data" / "reference_documents.csv", encoding="utf-8", newline="") as f:
        for d in csv.DictReader(f):
            for s in _sections(d):
                cite = f"{d['doc_id']} {s['section']}".strip()
                rows.append((len(rows) + 1, d["doc_id"], s["section"], s["heading"], d["version"],
                             not d["superseded_by"], d["superseded_by"] or None, d["language"], d["doc_type"],
                             cite, s["text"]))
    idx.execute("CREATE TABLE doc_sections (id INT, doc_id VARCHAR, section VARCHAR, heading VARCHAR, "
                "version VARCHAR, is_current BOOLEAN, superseded_by VARCHAR, language VARCHAR, doc_type VARCHAR, "
                "citation VARCHAR, text VARCHAR)")
    idx.executemany("INSERT INTO doc_sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    idx.execute("PRAGMA create_fts_index('doc_sections', 'id', 'heading', 'text', stemmer = 'english', "
                "overwrite = 1)")

    con = connect(read_only=True)
    notes = con.execute("SELECT note_id, case_id, note_ts, note_type, note_text FROM bronze.agent_notes "
                        "WHERE note_text IS NOT NULL AND coalesce(redaction_status, '') <> 'needs_review'").df()
    con.close()
    notes["note_text"] = [redact(t) for t in notes.note_text]
    idx.register("notes_df", notes)
    idx.execute("CREATE TABLE notes AS SELECT row_number() OVER () AS id, * FROM notes_df")
    idx.execute("PRAGMA create_fts_index('notes', 'id', 'note_text', stemmer = 'english', overwrite = 1)")
    n_doc = idx.execute("SELECT count(*) FROM doc_sections").fetchone()[0]
    n_note = idx.execute("SELECT count(*) FROM notes").fetchone()[0]
    idx.close()
    print(f"search index: {n_doc} document sections, {n_note:,} notes -> {INDEX_PATH}")


_IDX = None


def _index():
    global _IDX
    if _IDX is None:
        if not INDEX_PATH.exists():
            raise FileNotFoundError("search index missing: run `python -m ontrack.l2_ask.search --build`")
        _IDX = duckdb.connect(str(INDEX_PATH), read_only=True)
        _IDX.execute("LOAD fts")
    return _IDX.cursor()


def search_docs(query: str, k: int = 5, current_only: bool = False) -> list[dict]:
    # Policies and programme terms outrank FAQs and scripts when they disagree (the FAQ lags policy changes).
    weight = ("CASE doc_type WHEN 'policy' THEN 1.3 WHEN 'hardship_programme_terms' THEN 1.2 WHEN 'procedure' "
              "THEN 1.2 WHEN 'regulatory_summary' THEN 1.2 WHEN 'faq' THEN 0.8 WHEN 'call_script' THEN 0.8 ELSE 1.0 END")
    sql = ("SELECT citation, doc_id, section, heading, version, is_current, superseded_by, doc_type, text, score FROM "
           f"(SELECT *, fts_main_doc_sections.match_bm25(id, ?) * {weight} AS score FROM doc_sections) "
           "WHERE score IS NOT NULL" + (" AND is_current" if current_only else "")
           + " ORDER BY is_current DESC, score DESC LIMIT ?")
    df = _index().execute(sql, [query, int(k)]).df()
    return df.to_dict("records")


def search_notes(query: str, k: int = 10, case_id: str | None = None) -> list[dict]:
    sql = ("SELECT note_id, case_id, note_ts, note_type, note_text, score FROM "
           "(SELECT *, fts_main_notes.match_bm25(id, ?) AS score FROM notes) WHERE score IS NOT NULL"
           + (" AND case_id = ?" if case_id else "") + " ORDER BY score DESC LIMIT ?")
    params = [query] + ([case_id] if case_id else []) + [int(k)]
    df = _index().execute(sql, params).df()
    for r in (recs := df.to_dict("records")):
        r["citation"] = f"note {r['note_id']} (case {r['case_id']})"
    return recs


def format_hits(hits: list[dict], kind: str) -> str:
    if not hits:
        return "No matches."
    if kind == "docs":
        return "\n\n".join(f"[{h['citation']}] {h['heading']} · v{h['version']}"
                           + ("" if h["is_current"] else f" · SUPERSEDED by {h['superseded_by']}")
                           + f"\n{h['text']}" for h in hits)
    return "\n".join(f"[{h['citation']}] {h['note_ts']} {h['note_type']}: {h['note_text']}" for h in hits)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cited search over documents and notes")
    ap.add_argument("query", nargs="?")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--notes", action="store_true", help="search agent notes instead of documents")
    ap.add_argument("--case", default=None)
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args(argv)
    if args.build:
        build()
    if args.query:
        hits = search_notes(args.query, args.k, args.case) if args.notes else search_docs(args.query, args.k)
        print(format_hits(hits, "notes" if args.notes else "docs"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
