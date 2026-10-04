"""Pre-submission check: answers-file validation and README link parsing (no data needed)."""
import csv
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_submission", Path(__file__).resolve().parents[1] / "scripts" / "check_submission.py")
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)


def _write(path, rows, header=cs.ANSWER_COLUMNS):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_valid_answers_pass(tmp_path):
    p = tmp_path / "a.csv"
    _write(p, [["BQ-001", "No.", "doc §1", "false"], ["BQ-002", "Refused: protected attribute", "", "true"]])
    assert cs.check_answers(p, ["BQ-001", "BQ-002"]) == []


def test_answer_problems_are_reported(tmp_path):
    p = tmp_path / "a.csv"
    _write(p, [["BQ-001", "", "", "false"], ["BQ-001", "x", "", "yes"],
               ["BQ-009", "Not answered: no LLM configured", "", "false"]])
    problems = " | ".join(cs.check_answers(p, ["BQ-001", "BQ-002"]))
    for expected in ("duplicate question ids", "refused is not true/false", "empty answers",
                     "'Not answered'", "without an answer row: ['BQ-002']", "unknown question ids: ['BQ-009']"):
        assert expected in problems


def test_wrong_columns_fail(tmp_path):
    p = tmp_path / "a.csv"
    _write(p, [["BQ-001", "x"]], header=["question_id", "answer"])
    assert "columns" in cs.check_answers(p)[0]


def test_readme_links_skip_external_and_anchors():
    text = "[a](docs/x.md) [b](https://example.com) [c](#setup) [d](README.md#run)"
    assert cs.readme_links(text) == ["docs/x.md", "README.md"]


def test_blank_question_row_is_expected(tmp_path):
    p = tmp_path / "a.csv"
    _write(p, [["BQ-001", "No.", "", "false"], ["XQ-9", cs.BLANK_QUESTION_ANSWER, "", "false"]])
    assert cs.check_answers(p, ["BQ-001", "XQ-9"]) == []


def test_question_ids_read_in_any_column_order(tmp_path):
    q = tmp_path / "q.csv"
    q.write_text("split;question_text;question_id\ntest;Is X ok?;BQ-001\ndev;How many?;BQ-002\n", encoding="cp1252")
    a = tmp_path / "a.csv"
    _write(a, [["BQ-001", "Yes.", "", "false"], ["BQ-002", "3", "SELECT 3", "false"]])
    from ontrack.l2_ask.run_benchmark import read_questions
    ids = [r["question_id"] for r in read_questions(q)]
    assert ids == ["BQ-001", "BQ-002"]
    assert cs.check_answers(a, ids) == []


def test_placeholder_pattern():
    assert cs.PLACEHOLDERS.findall("video: _link added 4 Oct_ and [TBD-P3] TODO")
    assert not cs.PLACEHOLDERS.findall("All numbers final; TBDX is not a placeholder")
