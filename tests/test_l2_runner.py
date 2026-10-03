"""Layer 2 runner: one row per question in template format, even when a question fails (owner: P2).

Uses a fake engine and connection: no dataset or LLM needed.
"""
import csv

from ontrack.l2_ask import ask, run_benchmark


class FakeEngine:
    context = ""

    def __init__(self, con, use_cache=True):
        pass

    def answer(self, question, **kw):
        if "boom" in question:
            raise RuntimeError("simulated failure")
        if "refuse" in question:
            return ask.Answer("Refuse: protected ground", "", True, "refuse")
        return ask.Answer("queue,n\na,1", "SELECT 1", False, "data")


def test_runner_writes_every_row(tmp_path, monkeypatch):
    qs = tmp_path / "q.csv"
    qs.write_text("question_id,question_text\nQ1,ok question\nQ2,boom question\nQ3,please refuse this\n",
                  encoding="utf-8")
    out = tmp_path / "answers.csv"
    monkeypatch.setattr(run_benchmark, "connect", lambda read_only=True: None)
    monkeypatch.setattr(run_benchmark.ask, "Engine", FakeEngine)
    monkeypatch.setattr(run_benchmark.config, "WORK_DIR", tmp_path)
    assert run_benchmark.main(["--questions", str(qs), "--out", str(out), "--workers", "2"]) == 0

    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert [r["question_id"] for r in rows] == ["Q1", "Q2", "Q3"]           # question order kept
    assert list(rows[0]) == ["question_id", "answer", "sql_or_sources", "refused"]
    assert rows[0]["refused"] == "false" and rows[0]["sql_or_sources"] == "SELECT 1"
    assert rows[1]["answer"].startswith("Could not answer")                 # failure still gets a row
    assert rows[2]["refused"] == "true"


def test_format_table_rounds_floats_cleanly():
    import pandas as pd
    df = pd.DataFrame({"k": ["a"], "rate_pct": [8.650000000001], "n": [3]})
    assert ask.format_table(df) == "k,rate_pct,n\na,8.65,3"
