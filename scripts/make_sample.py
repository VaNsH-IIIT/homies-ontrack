"""Build a consistent dev sample of the dataset for teammates with limited disk or RAM (owner: P1).

    python scripts/make_sample.py --pct 5 --out D:/maple_sample

Samples people by golden_id (needs a finished `python -m ontrack.l1_factory.build`), then keeps every
row that belongs to them in every table, so joins still work. The output has the same layout as the
release folder (data/*.csv, Hive-partitioned Parquet, schema/, labels/, files/docs, sampled transcript
JSON files), so a teammate only changes MAPLE_DATA_DIR in .env and every command runs unchanged.
Reference tables (agents, policies, metrics, benchmark questions, ...) are copied whole.
Share the zipped folder by Drive link; never commit it.
"""
import argparse
import json
import shutil
from pathlib import Path

from ontrack import config
from ontrack.db import connect

# table -> SQL filter on the sampled keys (temp tables s_crm, s_card, s_loan, s_cif, s_case, ...)
FILTERS = {
    "customers": "crm_customer_id IN (SELECT k FROM s_crm)",
    "card_accounts": "src_customer_ref IN (SELECT k FROM s_card)",
    "loan_accounts": "src_customer_ref IN (SELECT k FROM s_loan)",
    "deposit_accounts": "src_customer_ref IN (SELECT k FROM s_cif)",
    "external": "bank_subject_ref IN (SELECT k FROM s_cif)",
    "bureau_history": "bank_subject_ref IN (SELECT k FROM s_cif)",
    "collections_cases": "coll_customer_ref IN (SELECT k FROM s_crm)",
    "contact_history": "crm_customer_id IN (SELECT k FROM s_crm)",
    "promises_to_pay": "crm_customer_id IN (SELECT k FROM s_crm)",
    "agent_notes": "crm_customer_id IN (SELECT k FROM s_crm)",
    "call_transcripts": "crm_customer_id IN (SELECT k FROM s_crm)",
    "voice_samples": "transcript_id IN (SELECT transcript_id FROM bronze.call_transcripts WHERE crm_customer_id IN (SELECT k FROM s_crm))",
    "model_scores": "crm_customer_id IN (SELECT k FROM s_crm)",
    "offers": "case_id IN (SELECT k FROM s_case)",
    "case_assignment_history": "case_id IN (SELECT k FROM s_case)",
    "loan_instalments": "loan_id IN (SELECT k FROM s_loan_acct)",
    "card_statements": "card_account_id IN (SELECT k FROM s_card_acct)",
    "transactions": "account_id IN (SELECT k FROM s_acct)",
    "account_monthly_snapshot": "account_id IN (SELECT k FROM s_acct)",
    "salary_credit_history": "deposit_account_id IN (SELECT k FROM s_dep_acct)",
}


def main(pct: float, out: Path) -> None:
    src = config.DATA_DIR
    schema = json.loads((src / "schema" / "schema.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    con = connect(read_only=True)

    modulo = round(100 / pct)
    con.execute(f"CREATE TEMP TABLE s_gid AS SELECT DISTINCT golden_id FROM gold.customer_xref WHERE hash(golden_id) % {modulo} = 0")
    for name, system in (("s_crm", "crm"), ("s_card", "cards"), ("s_loan", "loans"), ("s_cif", "core_banking")):
        con.execute(f"CREATE TEMP TABLE {name} AS SELECT source_key AS k FROM gold.customer_xref "
                    f"WHERE system_ok AND golden_id IN (SELECT golden_id FROM s_gid)".replace("system_ok", f"source_system = '{system}'"))
    con.execute("CREATE TEMP TABLE s_case AS SELECT case_id AS k FROM bronze.collections_cases WHERE coll_customer_ref IN (SELECT k FROM s_crm)")
    con.execute("CREATE TEMP TABLE s_card_acct AS SELECT card_account_id AS k FROM bronze.card_accounts WHERE src_customer_ref IN (SELECT k FROM s_card)")
    con.execute("CREATE TEMP TABLE s_loan_acct AS SELECT loan_id AS k FROM bronze.loan_accounts WHERE src_customer_ref IN (SELECT k FROM s_loan)")
    con.execute("CREATE TEMP TABLE s_dep_acct AS SELECT deposit_account_id AS k FROM bronze.deposit_accounts WHERE src_customer_ref IN (SELECT k FROM s_cif)")
    con.execute("CREATE TEMP TABLE s_acct AS SELECT k FROM s_card_acct UNION SELECT k FROM s_loan_acct UNION SELECT k FROM s_dep_acct")

    for name, spec in schema.items():
        where = FILTERS.get(name, "true")
        if spec["format"] == "csv":
            dest = (out / spec["path"]).as_posix()
            con.execute(f"COPY (SELECT * FROM bronze.{name} WHERE {where}) TO '{dest}' (HEADER, DELIMITER ',')")
        else:
            dest = (out / spec["path"]).as_posix().rstrip("/")
            con.execute(f"COPY (SELECT * FROM bronze.{name} WHERE {where}) TO '{dest}' "
                        "(FORMAT PARQUET, PARTITION_BY (year), OVERWRITE_OR_IGNORE, COMPRESSION zstd)")
        n = con.execute(f"SELECT count(*) FROM bronze.{name} WHERE {where}").fetchone()[0]
        spec["rows"] = n
        print(f"{name:28s} {n:>10,d} rows", flush=True)

    # Transcript JSON files for the sampled calls.
    paths = [r[0] for r in con.execute(f"SELECT file_path FROM bronze.call_transcripts WHERE {FILTERS['call_transcripts']}").fetchall()]
    for p in paths:
        if p:
            # file_path is relative to the release's files/ folder (e.g. transcripts/2022/11/10295.json)
            rel = Path(p) if (src / p).exists() else Path("files") / p
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, target)
    print(f"transcript files copied: {len(paths):,d}")

    for folder in ("schema", "labels", "files/docs"):
        shutil.copytree(src / folder, out / folder, dirs_exist_ok=True)
    for f in ("README.md", "DATA_DICTIONARY.xlsx", "MANIFEST.csv"):
        shutil.copy2(src / f, out / f)
    # Row counts in the sample's schema.json match the sample, so bronze's count check passes.
    (out / "schema" / "schema.json").write_text(json.dumps(schema, indent=1), encoding="utf-8")
    con.close()
    print(f"\nSample written to {out}. Teammates set MAPLE_DATA_DIR={out.as_posix()} in .env.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a consistent dev sample")
    ap.add_argument("--pct", type=float, default=5.0, help="percent of people to keep (default 5)")
    ap.add_argument("--out", type=Path, required=True, help="output folder (outside the repo)")
    a = ap.parse_args()
    main(a.pct, a.out)
