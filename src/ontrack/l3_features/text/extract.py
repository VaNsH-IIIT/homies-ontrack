"""Build features.text_signals for open cases (owner: P2). Layer 3, text features.

    python -m ontrack.l3_features.text.extract                      # all notes + all transcripts, no LLM calls
    python -m ontrack.l3_features.text.extract --llm-transcripts 500 --workers 4   # + Claude on 500 more calls
    python -m ontrack.l3_features.text.extract --skip-transcripts   # notes only

Output (interface in README):
  features.text_signals       one row per note / transcript of an open case
  features.text_signals_case  one row per open case: latest hardship evidence, any dispute, latest stated payday
Every open-case transcript gets signals from the cheap model (trained on the 500 labelled calls); Claude's result
(quote verified in its turn) replaces it where one exists, so `model` says which produced each row. Claude results
are cached: a re-run sends only new transcripts, and only when --llm-transcripts asks for them.
The slow part only reads the database; the write at the end takes seconds (DuckDB allows one writer).
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd

from ontrack import config
from ontrack.db import connect
from ontrack.l3_features.text import signals as S

COLUMNS = ["source_type", "source_id", "contact_id", "case_id", "crm_customer_id", "event_ts", "hardship_signal",
           "hardship_level", "hardship_confidence", "evidence_quote", "evidence_turn_index", "stated_delay_reason",
           "stated_payday", "dispute_mentioned", "model", "prompt_version"]
OPEN = "SELECT case_id FROM bronze.collections_cases WHERE outcome IS NULL"


def note_signals(con) -> pd.DataFrame:
    t0 = time.time()
    model = S.train_notes_model(con)
    notes = con.execute(
        f"SELECT note_id, contact_id, case_id, crm_customer_id, note_ts, coalesce(note_text, '') AS note_text "
        f"FROM bronze.agent_notes WHERE case_id IN ({OPEN}) "
        f"AND coalesce(redaction_status, '') <> 'needs_review'").df()   # design: needs_review notes excluded
    preds = model.predict([S.redact(t) for t in notes.note_text])
    df = pd.DataFrame(preds)
    # stated_payday relative to the note's own date, not the snapshot
    df["stated_payday"] = [S.stated_payday(t, ts.date() if pd.notna(ts) else None)
                           for t, ts in zip(notes.note_text, notes.note_ts)]
    out = pd.DataFrame({
        "source_type": "note", "source_id": notes.note_id, "contact_id": notes.contact_id,
        "case_id": notes.case_id, "crm_customer_id": notes.crm_customer_id, "event_ts": notes.note_ts,
        "hardship_signal": df.hardship_signal, "hardship_level": df.hardship_level,
        "hardship_confidence": df.hardship_confidence, "evidence_quote": df.evidence_quote,
        "evidence_turn_index": pd.NA, "stated_delay_reason": df.stated_delay_reason,
        "stated_payday": df.stated_payday, "dispute_mentioned": df.dispute_mentioned,
        "model": "notes-char-ngram-logreg (public_500)", "prompt_version": S.PROMPT_VERSION,
    })
    print(f"notes: {len(out):,} scored in {time.time() - t0:.0f}s; hardship {out.hardship_signal.mean():.1%}",
          flush=True)
    return out


def transcript_signals(con, llm_n: int, workers: int, batch_size: int) -> pd.DataFrame:
    """Every open-case transcript gets signals from the cheap model; Claude's (verified-quote) result replaces it
    where one exists: cached from earlier runs, plus the `llm_n` most recent transcripts not yet done."""
    meta = con.execute(
        f"SELECT transcript_id, contact_id, case_id, crm_customer_id, call_start_ts, call_end_ts, file_path "
        f"FROM bronze.call_transcripts WHERE case_id IN ({OPEN}) ORDER BY call_start_ts DESC").df()
    meta["transcript_id"] = meta.transcript_id.astype(str)
    t0 = time.time()
    items = [S.load_transcript(fp) for fp in meta.file_path]
    model = S.train_transcript_model(con)
    cheap = {r["transcript_id"]: r for r in model.predict(items)}
    print(f"transcripts: {len(items):,} scored by the cheap model in {time.time() - t0:.0f}s", flush=True)

    claude = S.extract_transcripts(items, cache_only=True)
    todo = [t for t in items if str(t["transcript_id"]) not in claude][:max(0, llm_n)]
    if todo:
        chunks = [todo[i:i + batch_size * 4] for i in range(0, len(todo), batch_size * 4)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for f in as_completed([pool.submit(S.extract_transcripts, c, batch_size) for c in chunks]):
                claude.update(f.result())
    print(f"transcripts: {len(claude):,} with Claude results (cached + new), {len(items) - len(claude):,} "
          f"cheap model only", flush=True)

    rows = []
    for m in meta.itertuples():
        r, src = (claude[m.transcript_id], f"claude {S.TEXT_MODEL}") if m.transcript_id in claude else             (cheap[m.transcript_id], "transcripts-char-ngram-logreg (public_500)")
        rows.append({
            "source_type": "transcript", "source_id": m.transcript_id, "contact_id": m.contact_id,
            "case_id": m.case_id, "crm_customer_id": m.crm_customer_id, "event_ts": m.call_end_ts,
            "hardship_signal": r["hardship"] != "none", "hardship_level": r["hardship"],
            "hardship_confidence": float(r.get("hardship_confidence") or 0),
            "evidence_quote": r.get("evidence_quote"), "evidence_turn_index": r.get("evidence_turn_index"),
            "stated_delay_reason": r.get("stated_delay_reason"),
            "stated_payday": _iso_or_none(r.get("stated_payday")),
            "dispute_mentioned": bool(r.get("dispute_mentioned")), "model": src,
            "prompt_version": S.PROMPT_VERSION,
        })
    out = pd.DataFrame(rows)
    print(f"transcripts: {len(out):,} rows; hardship {out.hardship_signal.mean() if len(out) else 0:.1%}",
          flush=True)
    return out


def _iso_or_none(s):
    try:
        return date.fromisoformat(str(s)).isoformat() if s else None
    except ValueError:
        return None


CASE_ROLLUP = """
CREATE OR REPLACE TABLE features.text_signals_case AS
WITH s AS (SELECT *, row_number() OVER (PARTITION BY case_id ORDER BY hardship_signal DESC, event_ts DESC) AS rk
           FROM features.text_signals)
SELECT case_id, any_value(crm_customer_id) AS crm_customer_id,
       bool_or(hardship_signal) AS text_hardship_any,
       bool_or(hardship_signal AND event_ts >= TIMESTAMP '{snap}' - INTERVAL 90 DAY) AS text_hardship_90d,
       max(hardship_confidence) FILTER (WHERE hardship_signal) AS text_hardship_confidence,
       max(event_ts) FILTER (WHERE hardship_signal) AS text_hardship_last_ts,
       any_value(evidence_quote) FILTER (WHERE rk = 1 AND hardship_signal) AS text_hardship_evidence,
       any_value(source_type || ':' || source_id) FILTER (WHERE rk = 1 AND hardship_signal) AS text_hardship_source,
       bool_or(dispute_mentioned) AS text_dispute_any,
       max(stated_payday) AS text_stated_payday_latest,
       count(*) AS text_sources
FROM s GROUP BY case_id
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build features.text_signals")
    ap.add_argument("--llm-transcripts", "--max-transcripts", dest="llm_transcripts", type=int, default=0,
                    help="also send the N most recent not-yet-extracted transcripts to Claude (cache reused)")
    ap.add_argument("--skip-transcripts", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args(argv)

    con = connect(read_only=True)
    parts = [note_signals(con)]
    if not args.skip_transcripts:
        parts.append(transcript_signals(con, args.llm_transcripts, args.workers, args.batch_size))
    con.close()
    df = pd.concat(parts, ignore_index=True)[COLUMNS]
    df["evidence_turn_index"] = pd.to_numeric(df.evidence_turn_index, errors="coerce").astype("Int64")
    df["stated_payday"] = pd.to_datetime(df.stated_payday, errors="coerce").dt.date
    staged = config.WORK_DIR / "text_signals.parquet"
    df.to_parquet(staged, index=False)

    con = connect()                                    # short write
    con.execute(f"CREATE OR REPLACE TABLE features.text_signals AS SELECT * FROM read_parquet('{staged.as_posix()}')")
    con.execute(CASE_ROLLUP.format(snap=config.SNAPSHOT_DATE))
    n, cases, hard = con.execute("SELECT count(*), count(DISTINCT case_id), sum(hardship_signal::INT) "
                                 "FROM features.text_signals").fetchone()
    nc, hc = con.execute("SELECT count(*), sum(text_hardship_90d::INT) FROM features.text_signals_case").fetchone()
    print(f"features.text_signals: {n:,} rows, {cases:,} open cases, {hard:,} with a hardship signal")
    print(f"features.text_signals_case: {nc:,} cases, {hc:,} with text hardship in the last 90 days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
