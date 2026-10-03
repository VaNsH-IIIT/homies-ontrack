"""SQL guard for Ask (owner: P2). Every query passes through `check()` before it runs.

Rules (design, Layer 2 step 4):
  * one statement, SELECT only (WITH / UNION allowed; no DDL, DML, PRAGMA, ATTACH, COPY, file readers);
  * only allow-listed tables (gold.*, features.*, in-scope bronze.*), only columns that exist there;
  * no protected attribute (config.PROTECTED_COLUMNS) and no direct-PII column anywhere in the query;
  * row cap: a LIMIT is added (or lowered) to ROW_CAP;
  * minimum group size: GROUP BY queries get HAVING count(*) >= MIN_GROUP so no group singles out a person.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from ontrack import config

ROW_CAP = 1000
MIN_GROUP = 10

# promises_to_pay is out of scope in our design (30 of 31 tables) for features and decisions. Six benchmark
# questions need it (BENCHMARK_NOTES.md), so Ask reads it read-only, aggregates only, PII columns still blocked.
# Pending P1's decision: set ONTRACK_ASK_BLOCK_PTP=1 to return to the design's 30-table scope.
BLOCKED_TABLES = {"promises_to_pay"} if os.environ.get("ONTRACK_ASK_BLOCK_PTP") == "1" else set()
ALLOWED_SCHEMAS = ("gold", "features", "bronze")

# Direct PII: never returned or filtered on by Ask (contract rule Q7 keeps it out of gold too).
PII_PATTERN = re.compile(
    r"(^|_)(first_name|last_name|given_name|surname|full_name|middle_name|customer_name|name_raw|account_holder_name"
    r"|dob|dob_raw|date_of_birth|birth_date|phone|phone_raw|mobile|email|email_address|street|address|address_line\d?"
    r"|postal_code|postal_raw|national_id|national_id_hash|sin|sin_hash|card_number|pan|iban)($|_)"
)
UNSAFE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command,
                exp.Merge, exp.Copy, exp.Attach, exp.Detach, exp.Pragma, exp.Set, exp.Use, exp.Transaction)
FILE_FUNCS = re.compile(r"\b(read_csv\w*|read_parquet|read_json\w*|read_text|read_blob|glob|parquet_scan|"
                        r"csv_scan|sniff_csv|getenv|current_setting)\s*\(", re.I)


class GuardError(ValueError):
    """The query was rejected; `reason` is shown to the user and fed back to the LLM for repair."""


@dataclass
class Schema:
    """Allow-listed tables -> columns, read from the database once."""
    tables: dict[str, set[str]] = field(default_factory=dict)   # "gold.case_360" -> {cols}

    @classmethod
    def from_db(cls, con) -> "Schema":
        rows = con.execute(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            f"WHERE table_schema IN {ALLOWED_SCHEMAS} AND table_name NOT LIKE '\\_%' ESCAPE '\\'"
        ).fetchall()
        tables: dict[str, set[str]] = {}
        for schema, table, col in rows:
            if table in BLOCKED_TABLES:
                continue
            tables.setdefault(f"{schema}.{table}", set()).add(col.lower())
        return cls(tables)

    def allowed_columns(self, table: str) -> set[str]:
        return {c for c in self.tables.get(table, set()) if not is_sensitive(c)}


# Quasi-identifiers that are proxies for protected grounds or income (design: proxies stay out). Province, city
# and urban/rural stay usable: contact rules and the benchmark are provincial.
PROXY_COLUMNS = {"age", "age_band", "fsa", "postal_code", "postal_code_raw", "geo_lat", "geo_lon", "employer_name",
                 "fsa_income_index", "cardholder_postal_raw", "borrower_postal_raw", "holder_postal_raw",
                 "payroll_descriptor_raw", "raw_description", "salutation", "id_document_type"}


def _tagged_columns() -> set[str]:
    """Columns the data dictionary tags as Direct PII or Protected attribute (schema/schema.json)."""
    import json
    path = config.DATA_DIR / "schema" / "schema.json"
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    return {c["name"].lower() for t in schema.values() for c in t["columns"]
            if c.get("sensitivity") in ("Direct PII", "Protected attribute")}


_TAGGED = _tagged_columns()
SENSITIVE_COLUMNS = _TAGGED | PROXY_COLUMNS | set(config.PROTECTED_COLUMNS)


def is_sensitive(col: str) -> bool:
    c = col.lower()
    # The dictionary tags are authoritative; the name pattern is only a fallback when schema.json is missing
    # (it would also catch harmless columns such as consent_email).
    return c in SENSITIVE_COLUMNS or (not _TAGGED and bool(PII_PATTERN.search(c)))


def check(sql: str, schema: Schema, row_cap: int = ROW_CAP, min_group: int = MIN_GROUP) -> str:
    """Return the safe SQL to run (with LIMIT / HAVING added) or raise GuardError."""
    sql = sql.strip().rstrip(";")
    if FILE_FUNCS.search(sql):
        raise GuardError("Reading files or settings is not allowed; query the allow-listed tables only.")
    try:
        trees = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"SQL does not parse: {str(e).splitlines()[0]}") from e
    if len(trees) != 1 or trees[0] is None:
        raise GuardError("Exactly one SQL statement is allowed.")
    tree = trees[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise GuardError("Only SELECT queries are allowed.")
    for node in tree.walk():
        if isinstance(node, UNSAFE_NODES):
            raise GuardError(f"{type(node).__name__} statements are not allowed (read-only).")

    # Tables: CTE names are local; everything else must be allow-listed and schema-qualified.
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used: list[str] = []
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not t.db and name in ctes:
            continue
        if isinstance(t.this, exp.Anonymous) or not name:
            raise GuardError("Table functions are not allowed.")
        full = f"{(t.db or '').lower()}.{name}"
        if name in BLOCKED_TABLES:
            raise GuardError(f"Table {name} is out of scope for our system.")
        if full not in schema.tables:
            raise GuardError(f"Table {full} is not allow-listed. Use one of the gold/features/bronze tables "
                             "with its schema prefix, e.g. gold.case_360.")
        used.append(full)

    # Columns: no protected or PII column anywhere (select list, filters, joins, ordering).
    known = set().union(*(schema.tables[t] for t in used)) if used else set()
    aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)}
    for c in tree.find_all(exp.Column):
        name = c.name.lower()
        if is_sensitive(name):
            kind = ("a protected attribute" if name in config.PROTECTED_COLUMNS else
                    "a proxy for protected grounds" if name in PROXY_COLUMNS else "direct personal information")
            raise GuardError(f"Column {name} is {kind} and cannot be used.")
        if name and used and name not in known and name not in aliases and name not in ctes and not _cte_col(tree, name):
            raise GuardError(f"Column {name} does not exist in {', '.join(sorted(set(used)))}.")
    if any(isinstance(s, exp.Star) for s in _select_exprs(tree)):
        for t in used:
            if any(is_sensitive(c) for c in schema.tables[t]):
                raise GuardError(f"SELECT * on {t} would return protected or personal columns; list the columns.")

    # Minimum group size on the outermost grouped select.
    if min_group and isinstance(tree, exp.Select) and tree.args.get("group"):
        cond = exp.condition(f"count(*) >= {int(min_group)}")
        having = tree.args.get("having")
        tree.set("having", exp.Having(this=exp.and_(having.this, cond) if having else cond))

    # Row cap.
    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError, TypeError):
            current = None
    if current is None or current > row_cap:
        tree = tree.limit(row_cap)
    return tree.sql(dialect="duckdb")


def _select_exprs(tree):
    for s in tree.find_all(exp.Select):
        yield from s.expressions


def _cte_col(tree, name: str) -> bool:
    """A column exposed by a CTE or subquery select list (so outer queries may reference it)."""
    for node in tree.find_all(exp.CTE, exp.Subquery):
        for s in node.find_all(exp.Select):
            if any(e.alias_or_name.lower() == name for e in s.expressions):
                return True
    return False
