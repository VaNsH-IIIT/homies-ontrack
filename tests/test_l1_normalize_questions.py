"""19:00 questions-file normaliser (P1): any shape in, clean UTF-8 out, released questions never lost."""
import csv
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "normalize_questions", Path(__file__).resolve().parents[1] / "scripts" / "normalize_questions.py")
nq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nq)

RELEASED = "question_id,question_text,difficulty,metric_id,as_of_date,tolerance,split\n" \
           "BQ-001,Is X ok?,easy,,2026-09-28,,dev\nBQ-002,How many?,easy,M1,2026-09-28,,test\n"


def _ids(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [r["question_id"] for r in csv.DictReader(f)]


def test_excel_file_with_only_new_questions_keeps_the_released_ones(tmp_path):
    rel = tmp_path / "rel.csv"
    rel.write_text(RELEASED, encoding="utf-8")
    extra = tmp_path / "extra.csv"
    extra.write_text("question_id ; question_text\r\nXQ-1;Combien en août ?\r\nXQ-1;dup\r\n\r\n", encoding="cp1252")
    out = tmp_path / "final.csv"
    assert nq.main([str(extra), str(out), "--append-released", str(rel)]) == 0
    assert _ids(out) == ["BQ-001", "BQ-002", "XQ-1"]
    assert "août" in out.read_text(encoding="utf-8")


def test_file_that_already_has_the_released_questions_is_not_doubled(tmp_path):
    rel = tmp_path / "rel.csv"
    rel.write_text(RELEASED, encoding="utf-8")
    full = tmp_path / "full.csv"
    full.write_text(RELEASED + "XQ-2,New one,,,,,\n", encoding="utf-8")
    out = tmp_path / "final.csv"
    nq.main([str(full), str(out), "--append-released", str(rel)])
    assert _ids(out) == ["BQ-001", "BQ-002", "XQ-2"]
