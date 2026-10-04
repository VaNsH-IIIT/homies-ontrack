"""Layer 1 silver: each source system's identity format parses to the same shape (owner: P1).

Runs the real silver SQL on a few hand-made rows in an in-memory DuckDB (no dataset needed).
"""
from datetime import date

import duckdb
import pytest

from ontrack.l1_factory.silver import STEPS, dob, phone10, postal6, province, ALL_DOB_FORMATS


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA silver; CREATE SCHEMA bronze")
    yield c
    c.close()


def parties(con, step, table, rows, cols):
    con.execute(f"CREATE TABLE {table} ({', '.join(f'{c} VARCHAR' for c in cols)}, snapshot_date DATE)")
    for r in rows:
        con.execute(f"INSERT INTO {table} VALUES ({', '.join('?' * (len(cols) + 1))})", [*r, date(2026, 9, 28)])
    out = con.execute(STEPS[step]).df().set_index("source_key")
    return out


def test_card_name_formats(con):
    cols = ["src_customer_ref", "cardholder_name_raw", "cardholder_dob_raw", "cardholder_phone_raw", "cardholder_postal_raw"]
    df = parties(con, "card_parties", "silver.card_accounts", [
        ("C1", "A. VAUGHN", "05-01-1980", "(416) 555-0199", "m5v 2t6"),
        ("C2", "DAVE MOLINA", "05-01-1980", "416555xx99", "M5V2T6"),
        ("C3", "IYER/LOGAN", "05-01-1980", "", ""),
    ], cols)
    assert (df.loc["C1", "surname_std"], df.loc["C1", "given_std"]) == ("VAUGHN", "A")
    assert (df.loc["C2", "surname_std"], df.loc["C2", "given_std"]) == ("MOLINA", "DAVE")
    assert (df.loc["C3", "surname_std"], df.loc["C3", "given_std"]) == ("IYER", "LOGAN")
    assert df.loc["C1", "dob"].date() == date(1980, 1, 5)  # cards use DD-MM-YYYY
    assert df.loc["C1", "phone10"] == "4165550199" and df.loc["C2", "phone10"] == "416555xx99"  # masked digits kept
    assert df.loc["C1", "postal6"] == "M5V2T6"


def test_loan_name_formats(con):
    cols = ["src_customer_ref", "borrower_name_raw", "borrower_dob_raw", "borrower_phone_raw", "borrower_postal_raw"]
    df = parties(con, "loan_parties", "silver.loan_accounts", [
        ("B1", "Hélène Fournier", "1980/01/05", "", ""),
        ("B2", "VILLANUEVA MARY GRACE", "1980/01/05", "", ""),
    ], cols)
    assert (df.loc["B1", "surname_std"], df.loc["B1", "given_std"]) == ("FOURNIER", "HELENE")  # accents stripped
    assert (df.loc["B2", "surname_std"], df.loc["B2", "given_std"]) == ("VILLANUEVA", "MARY")  # all caps: surname first
    assert df.loc["B1", "dob"].date() == date(1980, 1, 5)


def test_deposit_name_formats(con):
    cols = ["src_customer_ref", "holder_name_raw", "holder_dob_raw", "holder_phone_raw", "holder_postal_raw"]
    df = parties(con, "deposit_parties", "silver.deposit_accounts", [
        ("0000000001", "DESJARDINS M F", "19800105", "", ""),
        ("0000000002", "DE LEON M L", "19800105", "", ""),
    ], cols)
    assert (df.loc["0000000001", "surname_std"], df.loc["0000000001", "given_std"]) == ("DESJARDINS", "M")
    assert df.loc["0000000002", "surname_std"] == "DE LEON"  # multi-word surname kept
    assert df.loc["0000000001", "dob"].date() == date(1980, 1, 5)


@pytest.mark.parametrize("raw", ["1980-01-05", "05-01-1980", "1980/01/05", "19800105", "Jan 05 1980"])
def test_dob_formats_all_parse_to_one_date(raw):
    assert duckdb.sql(f"SELECT {dob(repr(raw), *ALL_DOB_FORMATS)}").fetchone()[0] == date(1980, 1, 5)


def test_phone_and_postal_normalisation():
    assert duckdb.sql(f"SELECT {phone10(repr('+1 (416) 555-0199'))}").fetchone()[0] == "4165550199"
    assert duckdb.sql(f"SELECT {postal6(repr('k1a 0b1'))}").fetchone()[0] == "K1A0B1"
    assert duckdb.sql(f"SELECT {postal6(repr(''))}").fetchone()[0] is None


@pytest.mark.parametrize("raw,code", [("Ont.", "ON"), ("B.C.", "BC"), ("Alta.", "AB"), ("Quebec", "QC"), ("PQ", "QC"),
                                      ("Man.", "MB"), ("N.S.", "NS"), (" on ", "ON"), ("YT", "YT")])
def test_province_variants_become_two_letter_codes(raw, code):
    assert duckdb.sql(f"SELECT {province(repr(raw))}").fetchone()[0] == code


def test_province_null_stays_null():
    assert duckdb.sql(f"SELECT {province('NULL')}").fetchone()[0] is None
