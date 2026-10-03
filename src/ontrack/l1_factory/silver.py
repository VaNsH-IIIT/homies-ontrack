"""Silver: cleaned, standardised, current records (owner: P1).

    python -m ontrack.l1_factory.silver

Each source system stores identity fields in its own format; silver brings them to one shape
so Layer 1 matching can compare like with like:
  surname_std, given_std (first given name or initial), dob, phone10 (digits, 'x' kept where masked),
  postal6 (A1A1A1, no space), fsa (first 3).
Accounts keep their latest snapshot only. CRM keeps current, non-deleted rows.
Every issue found is counted into silver._dq_issues for the data quality report.
"""
from ontrack.db import connect

# Name helpers (DuckDB SQL expressions). All names: upper case, accents stripped.
def norm(expr: str) -> str:
    return f"nullif(trim(regexp_replace(upper(strip_accents({expr})), '[^A-Z\\- ,/.]', '', 'g')), '')"


def phone10(expr: str) -> str:
    return f"nullif(right(regexp_replace(lower({expr}), '[^0-9x]', '', 'g'), 10), '')"


def postal6(expr: str) -> str:
    return f"nullif(upper(regexp_replace({expr}, '[^A-Za-z0-9]', '', 'g')), '')"


def dob(expr: str, *formats: str) -> str:
    tries = ", ".join(f"try_strptime({expr}, '{f}')" for f in formats)
    return f"CAST(coalesce({tries}) AS DATE)"


ALL_DOB_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%Y%m%d", "%d/%m/%Y", "%b %d %Y", "%m/%d/%Y")


STEPS = {
    # ---------- CRM: current, non-deleted records (a person may have two CRM records) ----------
    "crm": f"""
        SELECT c.*,
               {norm('last_name')} AS surname_std,
               {norm("split_part(trim(first_name), ' ', 1)")} AS given_std,
               coalesce(date_of_birth, {dob('dob_raw', *ALL_DOB_FORMATS)}) AS dob,
               coalesce({phone10('primary_phone_e164')}, {phone10('primary_phone_raw')}) AS phone10,
               coalesce({postal6('postal_code')}, {postal6('postal_code_raw')}) AS postal6
        FROM bronze.customers c
        WHERE coalesce(is_deleted, false) = false
          AND (effective_to_ts IS NULL OR effective_to_ts >= TIMESTAMP '9999-01-01')
    """,
    # ---------- Accounts: latest snapshot per account ----------
    "card_accounts": """
        SELECT * FROM bronze.card_accounts
        QUALIFY row_number() OVER (PARTITION BY card_account_id ORDER BY snapshot_date DESC) = 1
    """,
    "loan_accounts": """
        SELECT * FROM bronze.loan_accounts
        QUALIFY row_number() OVER (PARTITION BY loan_id ORDER BY snapshot_date DESC) = 1
    """,
    "deposit_accounts": """
        SELECT * FROM bronze.deposit_accounts
        QUALIFY row_number() OVER (PARTITION BY deposit_account_id ORDER BY snapshot_date DESC) = 1
    """,
    # ---------- Party records per source system key (identity fields standardised) ----------
    # Cards: 'M. DESJARDINS' (initial + surname) or 'MARTIN/MELISSA' (surname/given); DOB DD-MM-YYYY
    "card_parties": f"""
        SELECT src_customer_ref AS source_key,
               CASE WHEN cardholder_name_raw LIKE '%/%' THEN {norm("split_part(cardholder_name_raw, '/', 1)")}
                    ELSE {norm("regexp_replace(cardholder_name_raw, '^[A-Za-z]\\.\\s*', '')")} END AS surname_std,
               CASE WHEN cardholder_name_raw LIKE '%/%' THEN {norm("split_part(split_part(cardholder_name_raw, '/', 2), ' ', 1)")}
                    ELSE {norm("regexp_extract(cardholder_name_raw, '^([A-Za-z])\\.', 1)")} END AS given_std,
               {dob('cardholder_dob_raw', '%d-%m-%Y', *ALL_DOB_FORMATS)} AS dob,
               {phone10('cardholder_phone_raw')} AS phone10,
               {postal6('cardholder_postal_raw')} AS postal6
        FROM silver.card_accounts
        QUALIFY row_number() OVER (PARTITION BY src_customer_ref ORDER BY snapshot_date DESC) = 1
    """,
    # Loans: 'Hélène Fournier' (given surname); DOB YYYY/MM/DD
    "loan_parties": f"""
        SELECT src_customer_ref AS source_key,
               {norm("regexp_extract(trim(borrower_name_raw), '([^ ]+)$', 1)")} AS surname_std,
               {norm("split_part(trim(borrower_name_raw), ' ', 1)")} AS given_std,
               {dob('borrower_dob_raw', '%Y/%m/%d', *ALL_DOB_FORMATS)} AS dob,
               {phone10('borrower_phone_raw')} AS phone10,
               {postal6('borrower_postal_raw')} AS postal6
        FROM silver.loan_accounts
        QUALIFY row_number() OVER (PARTITION BY src_customer_ref ORDER BY snapshot_date DESC) = 1
    """,
    # Deposits: 'DESJARDINS M F' (surname + initials); DOB YYYYMMDD; key = 10-digit CIF
    "deposit_parties": f"""
        SELECT src_customer_ref AS source_key,
               {norm("split_part(trim(holder_name_raw), ' ', 1)")} AS surname_std,
               {norm("split_part(trim(holder_name_raw), ' ', 2)")} AS given_std,
               {dob('holder_dob_raw', '%Y%m%d', *ALL_DOB_FORMATS)} AS dob,
               {phone10('holder_phone_raw')} AS phone10,
               {postal6('holder_postal_raw')} AS postal6
        FROM silver.deposit_accounts
        QUALIFY row_number() OVER (PARTITION BY src_customer_ref ORDER BY snapshot_date DESC) = 1
    """,
    # Bureau: 'DESJARDINS, MICHEL FRANCOIS'; address ends with postal code; key = CIF
    "bureau_parties": f"""
        SELECT bank_subject_ref AS source_key,
               {norm("split_part(subject_name_reported, ',', 1)")} AS surname_std,
               {norm("split_part(trim(split_part(subject_name_reported, ',', 2)), ' ', 1)")} AS given_std,
               {dob('CAST(subject_dob_reported AS VARCHAR)', *ALL_DOB_FORMATS)} AS dob,
               CAST(NULL AS VARCHAR) AS phone10,
               {postal6("regexp_extract(subject_address_reported, '([A-Za-z][0-9][A-Za-z] ?[0-9][A-Za-z][0-9])\\s*$', 1)")} AS postal6
        FROM bronze.external
        QUALIFY row_number() OVER (PARTITION BY bank_subject_ref ORDER BY pull_date DESC) = 1
    """,
}


DQ_CHECKS = [
    # (issue, table, SQL that counts affected records, how handled)
    ("CRM records marked deleted or superseded (SCD2 history rows)", "customers",
     "SELECT count(*) FROM bronze.customers WHERE coalesce(is_deleted,false) OR effective_to_ts < TIMESTAMP '9999-01-01'",
     "Excluded from silver; only current, non-deleted CRM rows kept"),
    ("CRM duplicate person records (duplicate_of_crm_id set)", "customers",
     "SELECT count(*) FROM silver.crm WHERE duplicate_of_crm_id IS NOT NULL",
     "Kept; linked to the surviving record in identity resolution (tier 1)"),
    ("CRM records without national_id_hash", "customers",
     "SELECT count(*) FROM silver.crm WHERE national_id_hash IS NULL",
     "Matched on name, DOB, phone and postal instead"),
    ("Dates of birth missing in the source", "all party sources",
     "SELECT (SELECT count(*) FROM bronze.customers WHERE dob_raw IS NULL AND date_of_birth IS NULL) "
     "+ (SELECT count(*) FROM bronze.card_accounts WHERE cardholder_dob_raw IS NULL) "
     "+ (SELECT count(*) FROM bronze.loan_accounts WHERE borrower_dob_raw IS NULL) "
     "+ (SELECT count(*) FROM bronze.deposit_accounts WHERE holder_dob_raw IS NULL) "
     "+ (SELECT count(*) FROM bronze.external WHERE subject_dob_reported IS NULL)",
     "Left null; matching falls back to name, phone and postal code"),
    ("Dates of birth present but unparseable in any known format", "all party sources",
     "SELECT (SELECT count(*) FROM silver.crm WHERE dob IS NULL AND dob_raw IS NOT NULL) "
     "+ (SELECT count(*) FROM silver.loan_parties p JOIN silver.loan_accounts a ON a.src_customer_ref = p.source_key WHERE p.dob IS NULL AND a.borrower_dob_raw IS NOT NULL) "
     "+ (SELECT count(*) FROM silver.deposit_parties p JOIN silver.deposit_accounts a ON a.src_customer_ref = p.source_key WHERE p.dob IS NULL AND a.holder_dob_raw IS NOT NULL)",
     "Left null and counted; matching falls back to the other fields"),
    ("CRM dob_raw in mixed formats (DD/MM/YYYY and 'Mon DD YYYY' alongside ISO)", "customers",
     "SELECT count(*) FROM bronze.customers WHERE dob_raw IS NOT NULL AND NOT regexp_matches(dob_raw, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')",
     "Parsed with an ordered list of formats; ISO date_of_birth preferred when present"),
    ("collections_cases.account_ids not a JSON list (bare id or ';'-separated)", "collections_cases",
     "SELECT count(*) FROM bronze.collections_cases WHERE account_ids IS NOT NULL AND account_ids NOT LIKE '[%'",
     "Parsed all three shapes (JSON list, bare id, ';'-separated) before building case-to-account links"),
    ("Card phone numbers partly masked with 'x'", "card_accounts",
     "SELECT count(*) FROM silver.card_parties WHERE phone10 LIKE '%x%'",
     "Masked digits treated as wildcards in matching"),
    ("Postal codes with inconsistent spacing or case", "all party sources",
     "SELECT count(*) FROM bronze.customers WHERE postal_code_raw IS NOT NULL AND postal_code_raw <> postal_code",
     "Normalised to A1A1A1 (postal6) and FSA"),
]


def main() -> None:
    con = connect()
    for name, sql in STEPS.items():
        con.execute(f"CREATE OR REPLACE TABLE silver.{name} AS {sql}")
        n = con.execute(f"SELECT count(*) FROM silver.{name}").fetchone()[0]
        print(f"silver.{name:18s} {n:>12,d} rows", flush=True)

    con.execute("CREATE OR REPLACE TABLE silver._dq_issues (issue VARCHAR, table_name VARCHAR, "
                "records_affected BIGINT, handling VARCHAR)")
    for issue, table, sql, handling in DQ_CHECKS:
        n = con.execute(sql).fetchone()[0]
        con.execute("INSERT INTO silver._dq_issues VALUES (?, ?, ?, ?)", [issue, table, n, handling])
        print(f"  DQ {n:>10,d}  {issue}", flush=True)
    con.close()


if __name__ == "__main__":
    main()
