"""Code .zip for the submission form (owner: P1): exactly the committed files of a git ref, nothing else.

    python scripts/make_submission_zip.py                 # fetches, then origin/main -> ../HOmiES_OnTrack_code.zip
    python scripts/make_submission_zip.py --ref HEAD --out D:/HOmiES_OnTrack_code.zip

Uses `git archive`, so data, DuckDB files, .env and anything git-ignored can never end up in the zip. Prints the size
and checks that the key deliverables are inside.
"""
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MUST_HAVE = ["README.md", "AI_TOOLS.md", "contracts/c360_customer.yaml", "docs/data_quality_report.md",
             "docs/architecture/architecture.pdf", "docs/architecture/architecture.png",
             "submission/benchmark_answers.csv", "scripts/run_all.py"]
FORBIDDEN = (".env", ".duckdb", ".parquet")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the code zip for the submission form")
    ap.add_argument("--ref", default="origin/main", help="git ref to archive (default: what is on GitHub)")
    ap.add_argument("--out", default=str(REPO.parent / "HOmiES_OnTrack_code.zip"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.ref.startswith("origin/"):
        subprocess.run(["git", "fetch", "-q", "origin"], cwd=REPO, check=True)   # the zip matches GitHub, not a stale branch
    subprocess.run(["git", "archive", "--format=zip", f"--prefix=homies-ontrack/", "-o", str(out), args.ref],
                   cwd=REPO, check=True)
    names = zipfile.ZipFile(out).namelist()
    inside = {n.split("/", 1)[1] for n in names if "/" in n}
    missing = [m for m in MUST_HAVE if m not in inside]
    leaked = [n for n in names if n.endswith(FORBIDDEN)]
    print(f"{out}  {out.stat().st_size / 1e6:.1f} MB, {len(names)} entries, ref {args.ref}")
    print(f"  deliverables inside: {len(MUST_HAVE) - len(missing)}/{len(MUST_HAVE)}" + (f"; missing {missing}" if missing else ""))
    print("  no data, DuckDB or .env files" if not leaked else f"  LEAKED: {leaked}")
    return 0 if not missing and not leaked else 1


if __name__ == "__main__":
    sys.exit(main())
