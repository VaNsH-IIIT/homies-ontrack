"""Layer 1 gold rules and the data contract (owner: P1)."""
import duckdb
import pytest
import yaml

from ontrack import config
from ontrack.l1_factory.gold import BUCKET_SQL


@pytest.mark.parametrize("dpd, bucket", [(None, None), (-3, "current"), (0, "current"), (1, "1-30"), (30, "1-30"),
                                         (31, "31-60"), (90, "61-90"), (91, "91-120"), (180, "151-180"), (181, "180+")])
def test_delinquency_bucket_is_derived_from_dpd(dpd, bucket):
    d = "NULL::INTEGER" if dpd is None else str(dpd)
    assert duckdb.sql(f"SELECT {BUCKET_SQL.format(d=d)}").fetchone()[0] == bucket


@pytest.fixture(scope="module")
def contract():
    return yaml.safe_load((config.REPO_ROOT / "contracts" / "c360_customer.yaml").read_text(encoding="utf-8"))


def test_contract_has_owner_refresh_uses_and_rules(contract):
    assert contract["id"].startswith("DC-COLL")
    for key in ("owner", "refresh", "schema", "quality", "allowed_uses", "prohibited_uses", "access"):
        assert contract.get(key), key
    assert [r["id"] for r in contract["quality"]] == [f"Q{i}" for i in range(1, 9)]
    for rule in contract["quality"]:
        assert rule["sql"].strip().upper().startswith(("SELECT", "WITH")) and "threshold" in rule and rule["on_failure"]


def test_contract_schema_has_no_protected_attribute(contract):
    columns = {c["name"] for c in contract["schema"]}
    assert not columns & config.PROTECTED_COLUMNS
