"""Shared DuckDB connection for every layer (owner: P1).

One local database file per person: $ONTRACK_WORK_DIR/ontrack.duckdb
Schemas: bronze (raw as delivered), silver (cleaned), gold (C360 data products),
features (Layer 3), l4 (decision log).
"""
import duckdb

from ontrack import config

DB_PATH = config.WORK_DIR / "ontrack.duckdb"
SCHEMAS = ("bronze", "silver", "gold", "features", "l4")


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the project database. Use read_only=True for apps and analysis."""
    if read_only and not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found: run `python -m ontrack.l1_factory.bronze` first")
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    tmp = config.WORK_DIR / "tmp"
    tmp.mkdir(exist_ok=True)
    con.execute(f"SET temp_directory = '{tmp.as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    if not read_only:
        for schema in SCHEMAS:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    return con
