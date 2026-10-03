"""Bronze: land every raw table as delivered (owner: P1).

    python -m ontrack.l1_factory.bronze                 # all tables
    python -m ontrack.l1_factory.bronze --tables customers,agents

CSV tables are read with every column as text, then cast to the type declared in
schema/schema.json with TRY_CAST, so nothing fails on bad values:
  * identifier and text columns stay VARCHAR (keeps leading zeros, keeps the 'NA' outcome code);
  * values that do not cast become NULL and are counted in bronze._cast_failures;
  * columns found in a file but not in the schema (schema drift) stay VARCHAR and are logged.
Parquet history tables are exposed as views (already typed and compressed).
Load results are written to bronze._load_log.
"""
import argparse
import json
import time

from ontrack import config
from ontrack.db import connect

FALLBACK_TYPES = {"string": "VARCHAR", "enum": "VARCHAR", "date": "DATE", "json": "VARCHAR"}


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_schema() -> dict:
    with open(config.DATA_DIR / "schema" / "schema.json", encoding="utf-8") as f:
        return json.load(f)


def target_type(col: dict) -> str:
    return col.get("physical_type") or FALLBACK_TYPES.get(col.get("type"), "VARCHAR")


def csv_reader(path: str) -> str:
    return f"read_csv('{path}', header = true, all_varchar = true, nullstr = '')"


def load_csv_table(con, name: str, spec: dict) -> dict:
    path = (config.DATA_DIR / spec["path"]).as_posix()
    src = csv_reader(path)
    file_cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()]
    declared = {c["name"]: target_type(c) for c in spec["columns"]}

    select, typed = [], []
    for c in file_cols:
        t = declared.get(c, "VARCHAR")
        if t == "VARCHAR":
            select.append(q(c))
        else:
            select.append(f"TRY_CAST({q(c)} AS {t}) AS {q(c)}")
            typed.append((c, t))
    con.execute(f"CREATE OR REPLACE TABLE bronze.{q(name)} AS SELECT {', '.join(select)} FROM {src}")

    # Count values that exist in the file but could not be cast to the declared type.
    if typed:
        parts = []
        for c, t in typed:
            bad = f"{q(c)} IS NOT NULL AND TRY_CAST({q(c)} AS {t}) IS NULL"
            parts.append(f"count(*) FILTER (WHERE {bad}), any_value({q(c)}) FILTER (WHERE {bad})")
        row = con.execute(f"SELECT {', '.join(parts)} FROM {src}").fetchone()
        for i, (c, t) in enumerate(typed):
            n, sample = row[2 * i], row[2 * i + 1]
            if n:
                con.execute("INSERT INTO bronze._cast_failures VALUES (?, ?, ?, ?, ?)", [name, c, t, n, sample])

    return {
        "file_cols": file_cols,
        "extra_cols": [c for c in file_cols if c not in declared],
        "missing_cols": [c for c in declared if c not in file_cols],
    }


def load_parquet_table(con, name: str, spec: dict) -> dict:
    path = (config.DATA_DIR / spec["path"]).as_posix().rstrip("/")
    con.execute(
        f"CREATE OR REPLACE VIEW bronze.{q(name)} AS "
        f"SELECT * FROM read_parquet('{path}/**/*.parquet', hive_partitioning = true, union_by_name = true)"
    )
    file_cols = [r[0] for r in con.execute(f"DESCRIBE bronze.{q(name)}").fetchall()]
    declared = [c["name"] for c in spec["columns"]]
    return {
        "file_cols": file_cols,
        "extra_cols": [c for c in file_cols if c not in declared and c != "year"],
        "missing_cols": [c for c in declared if c not in file_cols],
    }


def main(tables: list[str] | None = None) -> None:
    schema = load_schema()
    names = tables or list(schema)
    con = connect()
    con.execute("CREATE TABLE IF NOT EXISTS bronze._cast_failures (table_name VARCHAR, column_name VARCHAR, "
                "target_type VARCHAR, failed_count BIGINT, sample_value VARCHAR)")
    con.execute("CREATE TABLE IF NOT EXISTS bronze._load_log (table_name VARCHAR, kind VARCHAR, rows BIGINT, "
                "expected_rows BIGINT, n_columns INTEGER, extra_cols VARCHAR[], missing_cols VARCHAR[], "
                "seconds DOUBLE, loaded_at TIMESTAMP)")

    for name in names:
        spec = schema[name]
        start = time.time()
        con.execute("DELETE FROM bronze._cast_failures WHERE table_name = ?", [name])
        con.execute("DELETE FROM bronze._load_log WHERE table_name = ?", [name])
        is_csv = spec["format"] == "csv"
        info = load_csv_table(con, name, spec) if is_csv else load_parquet_table(con, name, spec)
        rows = con.execute(f"SELECT count(*) FROM bronze.{q(name)}").fetchone()[0]
        secs = time.time() - start
        con.execute(
            "INSERT INTO bronze._load_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, now())",
            [name, "table" if is_csv else "view", rows, spec.get("rows"), len(info["file_cols"]),
             info["extra_cols"], info["missing_cols"], round(secs, 1)],
        )
        flag = "" if rows == spec.get("rows") else f"  (expected {spec.get('rows')})"
        drift = f"  drift +{info['extra_cols']} -{info['missing_cols']}" if info["extra_cols"] or info["missing_cols"] else ""
        print(f"{name:28s} {rows:>12,d} rows  {secs:6.1f}s{flag}{drift}", flush=True)

    failures = con.execute("SELECT count(*), coalesce(sum(failed_count), 0) FROM bronze._cast_failures").fetchone()
    print(f"\nCast failures: {failures[0]} columns, {failures[1]:,} values (see bronze._cast_failures)")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Land raw tables into bronze")
    ap.add_argument("--tables", help="comma-separated subset of tables")
    args = ap.parse_args()
    main(args.tables.split(",") if args.tables else None)
