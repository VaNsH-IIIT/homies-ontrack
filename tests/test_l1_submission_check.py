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
