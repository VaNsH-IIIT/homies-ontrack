"""Entry point: build features, train, route, recommend (owner: P3).

    python -m ontrack.l4_nba.run              # full pipeline
    python -m ontrack.l4_nba.run --score-only # skip training, just score open cases

Decisions taken in the agent card are written by ``ontrack.app.common.record_decision`` (decisions.duckdb).
"""
from __future__ import annotations

import argparse
import time

from ontrack import config
from ontrack.db import connect


def main(score_only: bool = False) -> None:
    t0 = time.time()
    con = connect()

    if not score_only:
        from ontrack.l4_nba.models import train_all
        print("=" * 60 + "\nTraining (point-in-time, monthly as_of dates)\n" + "=" * 60, flush=True)
        results = train_all(con)
        print("\nModel summary (test as_of 2026-07-01):")
        for name, meta in results.items():
            print(f"  {name}: AUC={meta['auc_test']:.3f}  Brier={meta['brier_test_calibrated']:.4f}")

    print("\n" + "=" * 60 + "\nFeatures for the open book, hardship routing\n" + "=" * 60, flush=True)
    from ontrack.l3_features.structured.features import build_case_features
    build_case_features(con, config.SNAPSHOT_DATE)
    from ontrack.l4_nba.hardship import print_summary as routing_summary, route_cases
    routed = route_cases(con, config.SNAPSHOT_DATE)
    routing_summary(routed)

    print("\n" + "=" * 60 + "\nRecommendations\n" + "=" * 60, flush=True)
    from ontrack.l4_nba.ranker import build_recommendations, channel_economics, print_summary
    rec = build_recommendations(con, routed, config.SNAPSHOT_DATE)
    print_summary(rec, channel_economics(con, config.SNAPSHOT_DATE))

    print("\n--- 5 sample recommendations ---")
    for _, r in rec.sample(5, random_state=7).iterrows():
        print(f"{r['case_id']}  {r['action']} via {r['channel']} ({r['time_window']})")
        for k in ("reason_1", "reason_2", "reason_3", "counterfactual"):
            if r[k]:
                print(f"    - {r[k]}")

    con.close()
    print(f"\nDone in {time.time() - t0:.0f} s.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build features, train models, generate NBA recommendations")
    ap.add_argument("--score-only", action="store_true", help="Skip training; score with existing models")
    args = ap.parse_args()
    main(score_only=args.score_only)
