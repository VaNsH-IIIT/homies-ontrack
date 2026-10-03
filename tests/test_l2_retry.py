"""Runner --retry-failed: only failed or missing questions are re-run; good answers are kept (owner: P2)."""
import csv

from ontrack.l2_ask import ask, run_benchmark


class CountingEngine:
    asked = []
    context = ""

    def __init__(self, con, use_cache=True):
        pass

    def answer(self, question, **kw):
        CountingEngine.asked.append(question)
        return ask.Answer("fixed", "SELECT 1", False, "data")


def test_retry_failed_only_reruns_failures(tmp_path, monkeypatch):
    qs = tmp_path / "q.csv"
    qs.write_text("question_id,question_text\nQ1,good one\nQ2,failed one\nQ3,missing one\n", encoding="utf-8")
    out = tmp_path / "answers.csv"
    out.write_text('"question_id","answer","sql_or_sources","refused"\n"Q1","kept","S","false"\n'
                   '"Q2","Could not answer: internal error","","false"\n', encoding="utf-8")
    monkeypatch.setattr(run_benchmark, "connect", lambda read_only=True: None)
    monkeypatch.setattr(run_benchmark.ask, "Engine", CountingEngine)
    monkeypatch.setattr(run_benchmark.config, "WORK_DIR", tmp_path)
    assert run_benchmark.main(["--questions", str(qs), "--out", str(out), "--retry-failed", "--workers", "1"]) == 0
    rows = {r["question_id"]: r["answer"] for r in csv.DictReader(open(out, encoding="utf-8"))}
    assert rows == {"Q1": "kept", "Q2": "fixed", "Q3": "fixed"}
    assert sorted(CountingEngine.asked) == ["failed one", "missing one"]
