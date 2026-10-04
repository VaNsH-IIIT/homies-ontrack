"""Layer 1 bronze: typed landing of a tiny fake release folder (code owner: P1; tests by P3, K20). No dataset needed.

The claims tested are the ones the README and the DQ report make: identifiers keep their leading zeros, 'NA' stays a
real outcome code (not null), values that don't fit the declared type become null and are counted with an example,
schema drift (extra or missing columns) and row-count mismatches are logged, and reloading a table replaces its log.
"""
import json

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ontrack import config
from ontrack.l1_factory import bronze
from ontrack.l1_factory.probabilistic import features, mask

SCHEMA = {
    "contacts": {"format": "csv", "path": "data/contacts.csv", "rows": 4, "columns": [
        {"name": "contact_id", "type": "string"},
        {"name": "outcome_code", "type": "enum"},
        {"name": "amount", "type": "number", "physical_type": "DOUBLE"},
        {"name": "contact_date", "type": "date"},
        {"name": "rpc_flag", "type": "boolean", "physical_type": "BOOLEAN"},
        {"name": "retired_col", "type": "string"},                      # in the schema, not in the file
    ]},
    "bureau_history": {"format": "parquet", "path": "data/bureau_history/", "rows": 3, "columns": [
        {"name": "subject", "type": "string"}, {"name": "score", "type": "integer", "physical_type": "INTEGER"},
    ]},
}

CSV = """contact_id,outcome_code,amount,contact_date,rpc_flag,new_col
00042,NA,12.50,2026-09-01,true,x
00043,RPC,twelve,2026-09-02,false,y
00044,,,not a date,maybe,
00045,PTP,7,2026-09-03,,z
"""


@pytest.fixture()
def release(tmp_path, monkeypatch):
    root = tmp_path / "release"
    (root / "schema").mkdir(parents=True)
    (root / "schema" / "schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "contacts.csv").write_text(CSV, encoding="utf-8")
    for year, rows in ((2025, [("A", 700), ("B", 650)]), (2026, [("A", 710)])):
        part = root / "data" / "bureau_history" / f"year={year}"
        part.mkdir(parents=True)
        pq.write_table(pa.table({"subject": [r[0] for r in rows], "score": [r[1] for r in rows],
                                 "extra_feed_col": ["x"] * len(rows)}), part / "part-0.parquet")
    monkeypatch.setattr(config, "DATA_DIR", root)
    db = tmp_path / "landing.duckdb"   # not bronze.duckdb: the catalog name would clash with the schema
    c = duckdb.connect(str(db))
    c.execute("CREATE SCHEMA bronze")
    c.close()
    monkeypatch.setattr(bronze, "connect", lambda read_only=False: duckdb.connect(str(db), read_only=read_only))
    return db


def test_csv_lands_typed_without_losing_ids_or_na(release):
    bronze.main(["contacts"])
    con = duckdb.connect(str(release), read_only=True)
    rows = con.execute("SELECT contact_id, outcome_code, amount, contact_date, rpc_flag FROM bronze.contacts "
                       "ORDER BY contact_id").fetchall()
    assert [r[0] for r in rows] == ["00042", "00043", "00044", "00045"]           # leading zeros kept
    assert rows[0][1] == "NA" and rows[2][1] is None                              # 'NA' is a code; '' is null
    assert [r[2] for r in rows] == [12.5, None, None, 7.0]                        # 'twelve' could not be cast
    assert str(rows[0][3]) == "2026-09-01" and rows[2][3] is None
    assert [r[4] for r in rows] == [True, False, None, None]
    types = dict(con.execute("SELECT column_name, data_type FROM information_schema.columns "
                             "WHERE table_name = 'contacts'").fetchall())
    assert types["contact_id"] == "VARCHAR" and types["amount"] == "DOUBLE" and types["contact_date"] == "DATE"
    assert types["new_col"] == "VARCHAR"                                          # drift column kept as text
    con.close()


def test_cast_failures_are_counted_with_an_example(release):
    bronze.main(["contacts"])
    con = duckdb.connect(str(release), read_only=True)
    got = {r[0]: r[1:] for r in con.execute(
        "SELECT column_name, target_type, failed_count, sample_value FROM bronze._cast_failures").fetchall()}
    assert got == {"amount": ("DOUBLE", 1, "twelve"), "contact_date": ("DATE", 1, "not a date"),
                   "rpc_flag": ("BOOLEAN", 1, "maybe")}
    con.close()


def test_load_log_records_drift_and_row_counts(release):
    bronze.main()
    con = duckdb.connect(str(release), read_only=True)
    log = {r[0]: r[1:] for r in con.execute(
        "SELECT table_name, kind, rows, expected_rows, extra_cols, missing_cols FROM bronze._load_log").fetchall()}
    assert log["contacts"] == ("table", 4, 4, ["new_col"], ["retired_col"])
    assert log["bureau_history"] == ("view", 3, 3, ["extra_feed_col"], [])      # partitions read; 'year' not drift
    con.close()


def test_reloading_a_table_replaces_its_log_rows(release, capsys):
    bronze.main(["contacts"])
    bronze.main(["contacts"])
    con = duckdb.connect(str(release), read_only=True)
    assert con.execute("SELECT count(*) FROM bronze._load_log").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM bronze._cast_failures").fetchone()[0] == 3
    con.close()
    out = capsys.readouterr().out
    assert "Cast failures: 3 columns, 3 values" in out


def test_row_count_mismatch_is_reported(release, capsys):
    schema = json.loads((config.DATA_DIR / "schema" / "schema.json").read_text(encoding="utf-8"))
    schema["contacts"]["rows"] = 5
    (config.DATA_DIR / "schema" / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    bronze.main(["contacts"])
    assert "(expected 5)" in capsys.readouterr().out


def test_identifiers_are_quoted():
    assert bronze.q('odd "name"') == '"odd ""name"""'
    assert bronze.target_type({"type": "date"}) == "DATE"
    assert bronze.target_type({"type": "number"}) == "VARCHAR"                    # unknown without a physical type
    assert bronze.target_type({"type": "string", "physical_type": "BIGINT"}) == "BIGINT"


# ---- probabilistic matching: the comparison features and the steward mask (Splink itself needs the data) ----

def test_splink_features_normalise_and_drop_masked_phones():
    con = duckdb.connect()
    row = con.execute(features("""SELECT 'card:1' AS uid, 'O''BRIEN-SMITH' AS surname_std, '  J.' AS given_std,
                                         DATE '1980-01-05' AS dob, '416555xx01' AS phone10, 'M5V2T6' AS postal6""")).fetchone()
    assert row == ("card:1", "OBRIENSMITH", "J", __import__("datetime").date(1980, 1, 5), None, "M5V2T6", "M5V")
    row = con.execute(features("""SELECT 'card:2' AS uid, '-' AS surname_std, NULL AS given_std, NULL::DATE AS dob,
                                         '4165550001' AS phone10, NULL AS postal6""")).fetchone()
    assert row[1:3] == (None, None) and row[4] == "4165550001" and row[6] is None
    con.close()


def test_steward_mask_shows_only_the_initial():
    con = duckdb.connect()
    exprs = ", ".join(mask(v) for v in ("'VAUGHN'", "NULL", "'A'"))
    assert con.execute(f"SELECT {exprs}").fetchone() == ("V•••••", None, "A")
    con.close()
