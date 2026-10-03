"""Evaluation: back-test and fairness analysis for Layer 4 (owner: P3).

    python -m ontrack.l4_nba.evaluation

Compares our NBA recommendations against the existing baseline
(bronze.nba_recommendation_last and bronze.model_scores).
Runs fairness checks on recommended-action rates by protected group
(protected attributes used ONLY for testing, never in decisions).
"""
from __future__ import annotations

from ontrack import config
from ontrack.db import connect


def backtest_vs_baseline(con) -> dict:
    """Compare our recommendations against the baseline."""
    results = {}

    try:
        baseline_count = con.execute("SELECT count(*) FROM bronze.nba_recommendation_last").fetchone()[0]
        our_count = con.execute("SELECT count(*) FROM gold.nba_recommendation").fetchone()[0]
        results["baseline_cases"] = baseline_count
        results["our_cases"] = our_count
    except Exception:
        print("  (No baseline nba_recommendation_last available)")
        results["baseline_cases"] = 0
        results["our_cases"] = 0
        return results

    overlap = con.execute("""
        SELECT count(*) FROM gold.nba_recommendation r
        JOIN bronze.nba_recommendation_last b ON b.case_id = r.case_id
    """).fetchone()[0]
    results["overlap_cases"] = overlap

    if overlap > 0:
        agreement = con.execute("""
            SELECT count(*) FROM gold.nba_recommendation r
            JOIN bronze.nba_recommendation_last b ON b.case_id = r.case_id
            WHERE r.action = b.action
        """).fetchone()[0]
        results["action_agreement"] = agreement
        results["agreement_rate"] = round(agreement / overlap, 4)

        action_dist = con.execute("""
            SELECT 'ours' AS source, action, count(*) AS n
            FROM gold.nba_recommendation GROUP BY action
            UNION ALL
            SELECT 'baseline', action, count(*)
            FROM bronze.nba_recommendation_last GROUP BY action
            ORDER BY source, n DESC
        """).fetchdf()
        results["action_distribution"] = action_dist

    return results


def compare_model_scores(con) -> dict:
    """Compare our model scores against bronze.model_scores baseline."""
    results = {}

    try:
        baseline = con.execute("""
            SELECT model_name, count(*) AS n,
                   avg(score) AS avg_score,
                   stddev(score) AS std_score
            FROM bronze.model_scores
            GROUP BY model_name
        """).fetchdf()
        results["baseline_scores"] = baseline
    except Exception:
        print("  (No baseline model_scores available)")
        return results

    try:
        ours = con.execute("""
            SELECT 'self_cure_30d' AS model_name, count(*) AS n,
                   avg(p_cure_30d) AS avg_score
            FROM gold.nba_recommendation
            UNION ALL
            SELECT 'payment_7d', count(*), avg(p_payment_7d)
            FROM gold.nba_recommendation
        """).fetchdf()
        results["our_scores"] = ours
    except Exception:
        pass

    return results


def fairness_check(con) -> dict:
    """Check recommended-action rates by protected group (offline only).

    Protected attributes are read from bronze ONLY for fairness testing
    and are NEVER used in features or decisions.
    """
    results = {}

    protected_cols = []
    for col in config.PROTECTED_COLUMNS:
        try:
            con.execute(f"SELECT {col} FROM bronze.customers LIMIT 1")
            protected_cols.append(col)
        except Exception:
            pass

    if not protected_cols:
        print("  No protected columns found in bronze.customers")
        return results

    for col in protected_cols:
        try:
            dist = con.execute(f"""
                SELECT c.{col} AS group_value,
                       r.action,
                       count(*) AS n,
                       avg(r.score) AS avg_score,
                       avg(r.hardship_flag::INT) AS hardship_rate
                FROM gold.nba_recommendation r
                JOIN gold.case_360 cs ON cs.case_id = r.case_id
                JOIN bronze.customers c ON c.crm_customer_id = cs.crm_customer_id
                WHERE c.{col} IS NOT NULL
                GROUP BY c.{col}, r.action
                HAVING count(*) >= 10
                ORDER BY c.{col}, n DESC
            """).fetchdf()

            if not dist.empty:
                results[col] = dist

                action_rates = con.execute(f"""
                    SELECT c.{col} AS group_value,
                           count(*) AS total,
                           count(*) FILTER (WHERE r.action = 'call') * 100.0 / count(*) AS call_pct,
                           count(*) FILTER (WHERE r.action = 'do_nothing') * 100.0 / count(*) AS do_nothing_pct,
                           count(*) FILTER (WHERE r.hardship_flag) * 100.0 / count(*) AS hardship_pct,
                           avg(r.score) AS avg_score
                    FROM gold.nba_recommendation r
                    JOIN gold.case_360 cs ON cs.case_id = r.case_id
                    JOIN bronze.customers c ON c.crm_customer_id = cs.crm_customer_id
                    WHERE c.{col} IS NOT NULL
                    GROUP BY c.{col}
                    HAVING count(*) >= 10
                    ORDER BY total DESC
                """).fetchdf()

                results[f"{col}_rates"] = action_rates
        except Exception:
            pass

    return results


def write_evaluation_report(con) -> str:
    """Run all evaluations and write EVALUATION.md."""
    lines = ["# Layer 4 Evaluation\n"]

    lines.append("## Back-test vs baseline\n")
    bt = backtest_vs_baseline(con)
    lines.append(f"- Baseline recommendations: {bt.get('baseline_cases', 'N/A'):,}")
    lines.append(f"- Our recommendations: {bt.get('our_cases', 'N/A'):,}")
    lines.append(f"- Overlap cases: {bt.get('overlap_cases', 'N/A'):,}")
    if "agreement_rate" in bt:
        lines.append(f"- Action agreement rate: {bt['agreement_rate']:.1%}")
    if "action_distribution" in bt:
        lines.append("\n### Action distribution\n")
        lines.append(bt["action_distribution"].to_markdown(index=False))
    lines.append("")

    lines.append("## Model scores comparison\n")
    ms = compare_model_scores(con)
    if "baseline_scores" in ms:
        lines.append("### Baseline model scores\n")
        lines.append(ms["baseline_scores"].to_markdown(index=False))
    if "our_scores" in ms:
        lines.append("\n### Our model scores\n")
        lines.append(ms["our_scores"].to_markdown(index=False))
    lines.append("")

    lines.append("## Fairness check\n")
    lines.append("Protected attributes used ONLY for offline testing, never in features or decisions.\n")
    fc = fairness_check(con)
    for key, df in fc.items():
        if key.endswith("_rates"):
            col = key.replace("_rates", "")
            lines.append(f"\n### Action rates by `{col}`\n")
            lines.append(df.to_markdown(index=False))
    lines.append("")

    report = "\n".join(lines)
    from pathlib import Path
    report_path = Path(__file__).parent / "EVALUATION.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nEvaluation report written to {report_path}")
    return report


def main():
    con = connect(read_only=True)
    write_evaluation_report(con)
    con.close()


if __name__ == "__main__":
    main()
