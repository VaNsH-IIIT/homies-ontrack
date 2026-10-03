"""Feedback loop: decisions plus the outcomes that followed become labels for the next model (owner: P1).

    python -m ontrack.feedback          (run by scripts/run_all.py after Layer 4)

"Outcomes improve the next recommendation": every decision is joined to what happened next.
Two sources of decisions:
  bank_history  the bank's previous engine: collections_cases.nba_recommendation_last, whether the agent
                accepted it or overrode it (and why), and the case outcome.
  ontrack       decisions agents record on the Agent card (decision_log in decisions.duckdb). Their outcome
                arrives with later data loads: label_status stays 'pending' until the data covers 30 days
                after the decision, then cured_30d is filled in on the next run.
Writes
  features.decision_feedback   one row per decision with its label (Layer 4 retraining reads label_status = 'known')
  features.override_summary    decisions, override share and 30-day cure rate per source, recommendation and action
"""
from ontrack import config
from ontrack.db import connect

DECISIONS_DB = config.WORK_DIR / "decisions.duckdb"  # written by the app
WINDOW_DAYS = 30

HISTORY_SQL = f"""
    SELECT 'bank_history' AS source, case_id, golden_id, case_open_date AS decided_as_of,
           nba_recommendation_last AS recommended_action,
           CASE WHEN human_override_flag THEN 'override' WHEN nba_accepted_flag THEN 'accept'
                WHEN NOT nba_accepted_flag THEN 'not_followed' ELSE 'unknown' END AS agent_action,
           override_reason AS reason, CAST(NULL AS VARCHAR) AS final_action,
           CASE WHEN case_open_date + INTERVAL {WINDOW_DAYS} DAY <= DATE '{{snapshot}}' THEN 'known' ELSE 'pending' END AS label_status,
           CASE WHEN case_open_date + INTERVAL {WINDOW_DAYS} DAY <= DATE '{{snapshot}}'
                THEN coalesce(cure_flag AND days_to_cure <= {WINDOW_DAYS}, false) END AS cured_30d,
           outcome
    FROM gold.case_360
    WHERE nba_recommendation_last IS NOT NULL
"""

ONTRACK_SQL = f"""
    SELECT 'ontrack' AS source, d.case_id, d.golden_id, CAST(d.ts AS DATE) AS decided_as_of,
           d.recommended_action, d.agent_action, d.reason_code AS reason, d.final_action,
           CASE WHEN CAST(d.ts AS DATE) + INTERVAL {WINDOW_DAYS} DAY <= DATE '{{snapshot}}' THEN 'known' ELSE 'pending' END,
           CASE WHEN CAST(d.ts AS DATE) + INTERVAL {WINDOW_DAYS} DAY <= DATE '{{snapshot}}'
                THEN coalesce(c.cure_flag AND c.cure_date > CAST(d.ts AS DATE)
                              AND c.cure_date <= CAST(d.ts AS DATE) + INTERVAL {WINDOW_DAYS} DAY, false) END,
           c.outcome
    FROM dec.decision_log d
    LEFT JOIN gold.case_360 c USING (case_id)
"""

SUMMARY_SQL = """
    SELECT source, recommended_action, agent_action, count(*) AS decisions,
           round(count(*) / sum(count(*)) OVER (PARTITION BY source, recommended_action), 4) AS share_of_recommendation,
           count(*) FILTER (WHERE label_status = 'known') AS with_outcome,
           round(avg(cured_30d::INT), 4) AS cure_rate_30d
    FROM features.decision_feedback
    GROUP BY source, recommended_action, agent_action ORDER BY source, decisions DESC
"""


def build(con, snapshot: str = config.SNAPSHOT_DATE, decisions_db=None) -> dict:
    """Write features.decision_feedback and features.override_summary; return row counts by source."""
    decisions_db = DECISIONS_DB if decisions_db is None else decisions_db
    con.execute("CREATE SCHEMA IF NOT EXISTS features")
    con.execute(f"CREATE OR REPLACE TABLE features.decision_feedback AS {HISTORY_SQL.format(snapshot=snapshot)}")
    if decisions_db.exists():
        try:
            con.execute(f"ATTACH '{decisions_db.as_posix()}' AS dec (READ_ONLY)")
        except Exception as e:  # the app may hold the file for a moment; picked up on the next run
            print(f"  decision log not read ({e.__class__.__name__}); picked up on the next run", flush=True)
        else:
            try:
                if con.execute("SELECT count(*) FROM information_schema.tables "
                               "WHERE table_catalog = 'dec' AND table_name = 'decision_log'").fetchone()[0]:
                    con.execute(f"INSERT INTO features.decision_feedback {ONTRACK_SQL.format(snapshot=snapshot)}")
            finally:
                con.execute("DETACH dec")
    con.execute(f"CREATE OR REPLACE TABLE features.override_summary AS {SUMMARY_SQL}")
    return dict(con.execute("SELECT source, count(*) FROM features.decision_feedback GROUP BY 1").fetchall())


def main() -> None:
    con = connect()
    counts = build(con)
    for source, n in sorted(counts.items()):
        known = con.execute("SELECT count(*) FROM features.decision_feedback WHERE source = ? AND label_status = 'known'",
                            [source]).fetchone()[0]
        print(f"  {source:13s} {n:>9,d} decisions, {known:>9,d} with a known 30-day outcome", flush=True)
    for src, action, n, cure in con.execute("""
            SELECT source, agent_action, count(*), round(avg(cured_30d::INT), 3) FROM features.decision_feedback
            GROUP BY 1, 2 ORDER BY 1, 3 DESC""").fetchall():
        print(f"  {src:13s} {action:13s} {n:>9,d}   cured within 30 days: {cure if cure is not None else 'pending'}", flush=True)
    con.close()


if __name__ == "__main__":
    main()
