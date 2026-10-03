"""Entry point: build features, train, recommend (owner: P3).

    python -m ontrack.l4_nba.run              # full pipeline
    python -m ontrack.l4_nba.run --score-only # skip training, just score open cases
"""
from __future__ import annotations

import argparse
import datetime as dt

from ontrack import config
from ontrack.db import connect


def main(score_only: bool = False) -> None:
    con = connect()

    from ontrack.l4_nba.ranker import create_decision_log
    create_decision_log(con)

    if not score_only:
        from ontrack.l4_nba.models import train_all
        print("=" * 60)
        print("Training models...")
        print("=" * 60)
        results = train_all(con)
        print("\nModel summary:")
        for name, meta in results.items():
            print(f"  {name}: AUC={meta['auc_val']:.4f}, Brier={meta['brier_val']:.4f}")

    print("\n" + "=" * 60)
    print("Generating recommendations for open cases...")
    print("=" * 60)

    as_of_ts = dt.datetime.fromisoformat(config.SNAPSHOT_DATE + "T12:00:00")
    from ontrack.l4_nba.ranker import build_recommendations
    n = build_recommendations(con, as_of_ts)

    print(f"\n{n:,d} recommendations written to gold.nba_recommendation")

    print("\n" + "=" * 60)
    print("Running hardship routing...")
    print("=" * 60)

    from ontrack.l4_nba.hardship import route_hardship_cases
    route_hardship_cases(con, as_of_ts)

    print("\nDone.")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build features, train models, generate NBA recommendations")
    ap.add_argument("--score-only", action="store_true", help="Skip training; score with existing models")
    args = ap.parse_args()
    main(score_only=args.score_only)
