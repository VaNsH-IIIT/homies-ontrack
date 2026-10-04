"""G17: the backup path can never drop the released questions (owner: P2). No dataset or LLM needed."""
import csv

from ontrack.l2_ask import backup_run

HEADER = "question_id,question_text,difficulty,metric_id,as_of_date,tolerance,split\n"


def _write(path, rows):
    path.write_text(HEADER + "".join(f"{i},{t},,,,,\n" for i, t in rows), encoding="utf-8")
    return path


def test_merge_puts_released_first_and_keeps_ids_once(tmp_path):
    rel = _write(tmp_path / "released.csv", [("BQ-001", "q1"), ("BQ-002", "q2")])
    org = _write(tmp_path / "extra.csv", [("BQ-002", "dup of released"), ("XQ-1", "new one")])   # overlaps
    dest = tmp_path / "final.csv"
    assert backup_run.merge_with_released(org, rel, dest) == (2, 1)
    ids = [r["question_id"] for r in csv.DictReader(open(dest, encoding="utf-8"))]
    assert ids == ["BQ-001", "BQ-002", "XQ-1"]                               # released first, once each


def test_validate_fails_when_released_ids_are_missing(tmp_path):
    q = _write(tmp_path / "extra_only.csv", [("XQ-1", "new one")])
    out = tmp_path / "answers.csv"
    out.write_text('"question_id","answer","sql_or_sources","refused"\n"XQ-1","ok","S","false"\n', encoding="utf-8")
    problems = backup_run.validate(q, out, required=["BQ-001", "BQ-002"])  # the K22 trap: ids match the file...
    assert any("released questions missing" in p for p in problems)        # ...but released ids are gone


def test_validate_ok_with_everything_present(tmp_path):
    q = _write(tmp_path / "final.csv", [("BQ-001", "q1"), ("XQ-1", "new one")])
    out = tmp_path / "answers.csv"
    out.write_text('"question_id","answer","sql_or_sources","refused"\n"BQ-001","a","S","false"\n'
                   '"XQ-1","b","S","true"\n', encoding="utf-8")
    assert backup_run.validate(q, out, required=["BQ-001"]) == []
