"""Build Layer 1 end to end: silver -> identity resolution -> gold -> data quality report (owner: P1).

    python -m ontrack.l1_factory.bronze     # once, after downloading the data
    python -m ontrack.l1_factory.build
"""
import time

from ontrack.l1_factory import dq, gold, identity, silver


def main() -> None:
    for step in (silver, identity, gold, dq):
        start = time.time()
        print(f"\n== {step.__name__.rsplit('.', 1)[-1]}", flush=True)
        step.main()
        print(f"   ({time.time() - start:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
