"""Run the quality rules of the data contract against the built gold tables (owner: P1).

    python -m ontrack.l1_factory.contract_check            # exit code 1 if a rule fails

Reads contracts/c360_customer.yaml; each rule's SQL returns a violation count (or a %) that must be
<= its threshold. Results go to gold._contract_results and the data quality report.
"""
import sys

import yaml

from ontrack import config
from ontrack.db import connect

CONTRACT = config.REPO_ROOT / "contracts" / "c360_customer.yaml"


def main() -> bool:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    con = connect()
    con.execute("CREATE OR REPLACE TABLE gold._contract_results (rule_id VARCHAR, rule_name VARCHAR, "
                "observed DOUBLE, threshold DOUBLE, passed BOOLEAN, on_failure VARCHAR, checked_at TIMESTAMP)")
    ok = True
    for rule in contract["quality"]:
        observed = float(con.execute(rule["sql"]).fetchone()[0] or 0)
        passed = observed <= float(rule["threshold"])
        ok &= passed
        con.execute("INSERT INTO gold._contract_results VALUES (?, ?, ?, ?, ?, ?, now())",
                    [rule["id"], rule["name"], observed, float(rule["threshold"]), passed, rule["on_failure"]])
        print(f"  {'PASS' if passed else 'FAIL'}  {rule['id']}  {rule['name']}: {observed:g} (<= {rule['threshold']})", flush=True)
    con.close()
    print(f"{contract['id']} v{contract['version']}: {'all rules passed' if ok else 'RULES FAILED'}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
