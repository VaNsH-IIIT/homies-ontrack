"""Run the whole system end to end, one command (owner: P1).

    python scripts/run_all.py                    # Layer 1 build -> benchmark -> NBA -> checks
    python scripts/run_all.py --with-bronze      # also (re)load the raw data first (~10 min full data)
    python scripts/run_all.py --skip-l1          # reuse the existing gold tables
    python scripts/run_all.py --transcripts 0    # no LLM calls: every note and call scored by the trained models

Steps whose module is not merged yet are reported as SKIPPED, so this works at every stage of the build.
Each step runs in its own process (as a judge would run it) and the summary shows what passed.
"""
import argparse
import importlib.util
import subprocess
import sys
import time

from ontrack import config


def module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Run OnTrack end to end")
    ap.add_argument("--with-bronze", action="store_true", help="reload raw data into bronze first")
    ap.add_argument("--skip-l1", action="store_true", help="skip the Layer 1 build (reuse gold)")
    ap.add_argument("--transcripts", type=int, default=300,
                    help="most recent calls also read by Claude (cached ones are free); every call is scored by the trained model either way; 0 = no LLM calls")
    args = ap.parse_args()

    questions = (config.DATA_DIR / "data" / "benchmark_questions.csv").as_posix()
    steps = []
    if args.with_bronze:
        steps.append(("L1 bronze: load raw data", "ontrack.l1_factory.bronze", []))
    if not args.skip_l1:
        steps.append(("L1 build: silver, identity (tiers 1-3), gold, contract, DQ report", "ontrack.l1_factory.build", []))
    steps += [
        ("L1 data contract check", "ontrack.l1_factory.contract_check", []),
        ("L3 text signals (all notes and calls; Claude on the most recent calls)", "ontrack.l3_features.text.extract",
         ["--llm-transcripts", str(args.transcripts), "--workers", "4"]),
        ("L4 features, models, recommendations", "ontrack.l4_nba.run", []),
        ("L2 benchmark answers", "ontrack.l2_ask.run_benchmark",
         ["--questions", questions, "--out", (config.REPO_ROOT / "benchmark" / "answers.csv").as_posix(), "--workers", "4"]),
    ]

    results = []
    for title, module, extra in steps:
        if not module_exists(module):
            results.append((title, "SKIPPED (not merged yet)", 0.0))
            print(f"\n=== {title}: SKIPPED ({module} not found)", flush=True)
            continue
        print(f"\n=== {title}  [python -m {module} {' '.join(extra)}]", flush=True)
        start = time.time()
        code = subprocess.call([sys.executable, "-m", module, *extra])
        results.append((title, "OK" if code == 0 else f"FAILED (exit {code})", time.time() - start))

    print("\n" + "=" * 72 + "\nSUMMARY")
    for title, status, secs in results:
        print(f"  {status:26s} {secs:7.0f}s  {title}")
    print("Then: streamlit run src/ontrack/app/main.py")
    return 0 if all(s.startswith(("OK", "SKIPPED")) for _, s, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
