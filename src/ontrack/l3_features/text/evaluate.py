"""Precision / recall of the text signals on the public labels (owner: P2).

    python -m ontrack.l3_features.text.evaluate                 # notes (5-fold CV) + 80 labelled transcripts
    python -m ontrack.l3_features.text.evaluate --transcripts 200

Design, Layer 3: an LLM feature ships only after clearing its target on labelled calls (hardship recall >= 90%).
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from ontrack.db import connect
from ontrack.l3_features.text import signals as S


def pr(y_true, y_pred) -> str:
    y_true, y_pred = np.asarray(y_true, bool), np.asarray(y_pred, bool)
    tp = int((y_true & y_pred).sum())
    p = tp / max(1, int(y_pred.sum()))
    r = tp / max(1, int(y_true.sum()))
    f = 2 * p * r / max(1e-9, p + r)
    return f"precision {p:.2f}  recall {r:.2f}  F1 {f:.2f}  (positives {int(y_true.sum())}/{len(y_true)})"


def evaluate_notes(con) -> None:
    from sklearn.model_selection import StratifiedKFold
    df = S.load_note_labels(con).reset_index(drop=True)
    preds = [None] * len(df)
    for train, test in StratifiedKFold(5, shuffle=True, random_state=7).split(df, df.hardship):
        m = S.NotesModel().fit(df.text[train].tolist(), df.hardship[train].tolist(), df.reason[train].tolist(),
                                df.evidence[train].tolist())
        for i, p in zip(test, m.predict(df.text[test].tolist())):
            preds[i] = p
    hs = [p["hardship_signal"] for p in preds]
    print(f"NOTES ({len(df)} labelled, 5-fold CV, char n-gram model)")
    print(f"  hardship_signal (clear|possible) : {pr(df.hardship != 'none', hs)}")
    print(f"  hardship clear only              : {pr(df.hardship == 'clear', [p['hardship_level'] == 'clear' for p in preds])}")
    acc = np.mean([p["stated_delay_reason"] == r for p, r in zip(preds, df.reason)])
    print(f"  stated_delay_reason accuracy     : {acc:.2f}")
    print(f"  dispute_mentioned (rule)         : {pr(df.dispute, [p['dispute_mentioned'] for p in preds])}")
    ev = [(p["evidence_quote"] or "") for p, h in zip(preds, df.hardship) if h != "none"]
    gold = [(e or "") for e, h in zip(df.evidence, df.hardship) if h != "none"]
    hit = np.mean([bool(g) and (g.lower() in e.lower() or e.lower() in g.lower()) for e, g in zip(ev, gold)])
    print(f"  evidence clause overlaps the labelled evidence: {hit:.0%} of hardship notes")


def evaluate_transcript_model(con) -> None:
    from sklearn.model_selection import StratifiedKFold
    lab = S.load_transcript_labels(con).reset_index(drop=True)
    docs = [S.load_transcript(fp) for fp in lab.file_path]
    preds = [None] * len(lab)
    for train, test in StratifiedKFold(5, shuffle=True, random_state=7).split(lab, lab.hardship):
        m = S.TranscriptModel().fit([docs[i] for i in train], lab.hardship[train].tolist(),
                                    lab.reason[train].tolist(), lab.dispute[train].tolist(),
                                    lab.evidence[train].tolist())
        for i, p in zip(test, m.predict([docs[i] for i in test])):
            preds[i] = p
    print(f"TRANSCRIPTS, cheap model ({len(lab)} labelled, 5-fold CV, char n-grams on customer turns)")
    print(f"  hardship_signal (clear|possible) : {pr(lab.hardship != 'none', [p['hardship'] != 'none' for p in preds])}")
    print(f"  hardship clear only              : {pr(lab.hardship == 'clear', [p['hardship'] == 'clear' for p in preds])}")
    acc = np.mean([p["stated_delay_reason"] == r for p, r in zip(preds, lab.reason)])
    print(f"  stated_delay_reason accuracy     : {acc:.2f}")
    print(f"  dispute_mentioned                : {pr(lab.dispute, [p['dispute_mentioned'] for p in preds])}")
    ev = [(p["evidence_quote"] or "", g if isinstance(g, str) else "") for p, g, h in
          zip(preds, lab.evidence, lab.hardship) if h != "none" and p["hardship"] != "none"]
    hit = np.mean([bool(g) and (g.lower()[:40] in e.lower() or e.lower() in g.lower()) for e, g in ev]) if ev else 0
    print(f"  evidence turn contains the labelled evidence: {hit:.0%} of hardship calls")


def evaluate_transcripts(con, n: int) -> None:
    p = S.TRANSCRIPT_LABELS.as_posix()
    lab = con.execute(
        f"SELECT l.transcript_id, t.file_path, l.label_hardship AS hardship, "
        f"coalesce(l.label_stated_delay_reason, 'other') AS reason, l.label_dispute = 'true' AS dispute "
        f"FROM read_csv('{p}', all_varchar = true) l JOIN bronze.call_transcripts t USING (transcript_id) "
        f"ORDER BY hash(l.transcript_id) LIMIT {int(n)}").df()
    items = [S.load_transcript(fp) for fp in lab.file_path]
    res = S.extract_transcripts(items)
    lab = lab[lab.transcript_id.isin(res)]
    got = [res[t] for t in lab.transcript_id]
    print(f"TRANSCRIPTS ({len(lab)} labelled, Claude {S.TEXT_MODEL})")
    print(f"  hardship_signal (clear|possible) : {pr(lab.hardship != 'none', [g['hardship'] != 'none' for g in got])}")
    print(f"  hardship clear only              : {pr(lab.hardship == 'clear', [g['hardship'] == 'clear' for g in got])}")
    acc = np.mean([g["stated_delay_reason"] == r for g, r in zip(got, lab.reason)])
    print(f"  stated_delay_reason accuracy     : {acc:.2f}")
    print(f"  dispute_mentioned                : {pr(lab.dispute, [g['dispute_mentioned'] for g in got])}")
    hard = [g for g in got if g["hardship"] != "none"]
    ok = np.mean([bool(g.get("evidence_quote")) for g in hard]) if hard else 0
    print(f"  evidence quote verified in its turn: {ok:.0%} of hardship calls")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", type=int, default=80, help="labelled transcripts to score with the LLM (0 = skip)")
    args = ap.parse_args(argv)
    con = connect(read_only=True)
    evaluate_notes(con)
    evaluate_transcript_model(con)
    if args.transcripts:
        evaluate_transcripts(con, args.transcripts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
