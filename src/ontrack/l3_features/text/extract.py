"""Build features.text_signals for open cases (owner: P2). Layer 3, text features.

    python -m ontrack.l3_features.text.extract                      # notes (all) + transcripts (LLM, cached)
    python -m ontrack.l3_features.text.extract --max-transcripts 500 --workers 6
    python -m ontrack.l3_features.text.extract --skip-transcripts   # notes only, ~2 min, no LLM

Output (interface in README):
  features.text_signals       one row per note / transcript of an open case
  features.text_signals_case  one row per open case: latest hardship evidence, any dispute, latest stated payday
Transcripts are processed most recent first and cached, so a re-run only sends new transcripts to the LLM; until
every transcript is done, the table holds the ones processed so far (coverage is printed).
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


def transcript_signals(con, max_n: int | None, workers: int, batch_size: int) -> pd.DataFrame:
    meta = con.execute(
        f"SELECT transcript_id, contact_id, case_id, crm_customer_id, call_end_ts, file_path "
        f"FROM bronze.call_transcripts WHERE case_id IN ({OPEN}) ORDER BY call_start_ts DESC").df()
    if max_n:
        meta = meta.head(max_n)
    t0 = time.time()
    items = [S.load_transcript(fp) for fp in meta.file_path]
    batches = [items[i:i + batch_size * 4] for i in range(0, len(items), batch_size * 4)]
    results: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(S.extract_transcripts, b, batch_size) for b in batches]
        for f in as_completed(futs):
            results.update(f.result())
            done += 1
            if done % 5 == 0 or done == len(futs):
                print(f"  transcripts: {len(results):,}/{len(items):,} in {time.time() - t0:.0f}s", flush=True)
    meta = meta[meta.transcript_id.astype(str).isin(results)]
    r = [results[str(t)] for t in meta.transcript_id]
    out = pd.DataFrame({
        "source_type": "transcript", "source_id": meta.transcript_id.astype(str), "contact_id": meta.contact_id,
        "case_id": meta.case_id, "crm_customer_id": meta.crm_customer_id, "event_ts": meta.call_end_ts,
        "hardship_signal": [x["hardship"] != "none" for x in r], "hardship_level": [x["hardship"] for x in r],
        "hardship_confidence": [float(x.get("hardship_confidence") or 0) for x in r],
        "evidence_quote": [x.get("evidence_quote") for x in r],
        "evidence_turn_index": [x.get("evidence_turn_index") for x in r],
        "stated_delay_reason": [x.get("stated_delay_reason") for x in r],
        "stated_payday": [_iso_or_none(x.get("stated_payday")) for x in r],
        "dispute_mentioned": [bool(x.get("dispute_mentioned")) for x in r],
        "model": f"claude {S.TEXT_MODEL}", "prompt_version": S.PROMPT_VERSION,
    })
    print(f"transcripts: {len(out):,} with signals; hardship {out.hardship_signal.mean() if len(out) else 0:.1%}",
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
    ap.add_argument("--max-transcripts", type=int, default=None, help="most recent N open-case transcripts")
    ap.add_argument("--skip-transcripts", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args(argv)

    con = connect(read_only=True)
    parts = [note_signals(con)]
    if not args.skip_transcripts:
        parts.append(transcript_signals(con, args.max_transcripts, args.workers, args.batch_size))
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
