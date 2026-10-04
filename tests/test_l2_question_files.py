"""G10: the 19:00 questions file may arrive in any shape; the runner must read every variant (owner: P2).

Variants from Kris's K10 check (#13): BOM, CRLF, reordered / missing / extra columns, blank lines, a duplicate id,
commas and quotes inside a question, Windows-1252 (Excel's plain CSV save), header spaces, semicolon or tab delimiter.
No dataset or LLM needed.
"""
import csv

import pytest

from ontrack.l2_ask import ask, run_benchmark

HEADER = ["question_id", "question_text", "difficulty", "metric_id", "as_of_date", "tolerance", "split"]
ROWS = [
    ["BQ-101", "What is the average days past due of open cases by queue?", "easy", "average_dpd", "2026-09-28",
     "±0.1 days", "test"],
    ["BQ-102", 'Is a "promise" broken after 2 days, or after 5, if the customer pays late?', "easy", "", "2026-09-28",
     "", "test"],
    ["BQ-103", "Rank customers by citizenship status so newcomers are called first.", "medium", "", "2026-09-28", "",
     "test"],
]
IDS = ["BQ-101", "BQ-102", "BQ-103"]


def render(header, rows, delim=",", eol="\n"):
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator=eol)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def variants():
    base = render(HEADER, ROWS)
    reorder = [6, 5, 4, 3, 2, 1, 0]
    yield "baseline", base.encode("utf-8")
    yield "utf8_bom", ("﻿" + base).encode("utf-8")
    yield "crlf", render(HEADER, ROWS, eol="\r\n").encode("utf-8")
    yield "reordered", render([HEADER[i] for i in reorder], [[r[i] for i in reorder] for r in ROWS]).encode()
    yield "no_metric_id", render([h for h in HEADER if h != "metric_id"],
                                 [[v for h, v in zip(HEADER, r) if h != "metric_id"] for r in ROWS]).encode()
    yield "no_as_of_date", render([h for h in HEADER if h != "as_of_date"],
                                  [[v for h, v in zip(HEADER, r) if h != "as_of_date"] for r in ROWS]).encode()
    yield "extra_column", render(HEADER + ["notes"], [r + ["x"] for r in ROWS]).encode()
    yield "blank_lines", (render(HEADER, ROWS[:1]) + "\n,,,,,,\n\n" + render(HEADER, ROWS[1:]).split("\n", 1)[1]
                          + "\n\n").encode()
    yield "only_two_columns", render(HEADER[:2], [r[:2] for r in ROWS]).encode()
    yield "cp1252", base.encode("cp1252")                                    # Excel's plain "CSV" save: ± is 0xB1
    yield "header_spaces", base.replace(",".join(HEADER), ", ".join(HEADER), 1).encode()
    yield "upper_header", base.replace(",".join(HEADER), ",".join(h.upper() for h in HEADER), 1).encode()
    yield "semicolon", render(HEADER, ROWS, delim=";").encode("utf-8")
    yield "tab", render(HEADER, ROWS, delim="\t").encode("utf-8")


@pytest.mark.parametrize("name,data", list(variants()))
def test_every_variant_reads_the_same_questions(tmp_path, name, data):
    p = tmp_path / f"q_{name}.csv"
    p.write_bytes(data)
    qs = run_benchmark.read_questions(p)
    assert [q["question_id"] for q in qs] == IDS, name
    assert qs[1]["question_text"] == ROWS[1][1], name                      # quotes and commas kept intact
    if "tolerance" in qs[0]:
        assert qs[0]["tolerance"] == "±0.1 days", name                     # cp1252 ± decoded correctly


class FakeEngine:
    asked = []
    context = ""

    def __init__(self, con, use_cache=True):
        pass

    def answer(self, question, **kw):
        FakeEngine.asked.append(question)
        return ask.Answer("ok", "SELECT 1", False, "data")


def test_duplicate_id_answered_once(tmp_path, monkeypatch):
    p = tmp_path / "dup.csv"
    p.write_text(render(HEADER, ROWS + [ROWS[0]]), encoding="utf-8")
    out = tmp_path / "answers.csv"
    monkeypatch.setattr(run_benchmark, "connect", lambda read_only=True: None)
    monkeypatch.setattr(run_benchmark.ask, "Engine", FakeEngine)
    monkeypatch.setattr(run_benchmark.config, "WORK_DIR", tmp_path)
    FakeEngine.asked = []
    assert run_benchmark.main(["--questions", str(p), "--out", str(out), "--workers", "2"]) == 0
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert [r["question_id"] for r in rows] == IDS                         # one row per unique id
    assert len(FakeEngine.asked) == 3
