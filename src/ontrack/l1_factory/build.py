"""Build Layer 1 end to end (owner: P1):
   silver -> identity (tiers 1-2) -> probabilistic (tier 3, Splink) -> identity (all tiers) -> gold -> data contract checks -> DQ report.

    python -m ontrack.l1_factory.bronze     # once, after downloading the data
    python -m ontrack.l1_factory.build
"""
import time

from ontrack.db import connect
from ontrack.l1_factory import contract_check, dq, gold, identity, probabilistic, silver


def main() -> None:
    con = connect()
    con.execute("DROP TABLE IF EXISTS silver.splink_edges")  # first identity pass uses tiers 1-2 only
    con.close()
    contract_ok = True
    for step in (silver, identity, probabilistic, identity, gold, contract_check, dq):
        start = time.time()
        print(f"\n== {step.__name__.rsplit('.', 1)[-1]}", flush=True)
        result = step.main()
        if step is contract_check:
            contract_ok = result is not False   # contract_check.main() returns True / False
        print(f"   ({time.time() - start:.0f}s)", flush=True)
    if not contract_ok:   # the contract says "block build": the DQ report is still written, then the build fails
        raise SystemExit("Data contract failed: see the FAIL rules above and docs/data_quality_report.md")


if __name__ == "__main__":
    main()
