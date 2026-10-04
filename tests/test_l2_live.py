"""G21: live-question resilience on the Ask page (owner: P2). No dataset or LLM needed: the agent is stubbed."""
import time

import duckdb
import pytest

from ontrack.l2_ask import ask, llm


@pytest.fixture
def eng(monkeypatch):
    con = duckdb.connect()
    con.execute("CREATE SCHEMA bronze")
    con.execute("CREATE TABLE bronze.collections_cases AS SELECT * FROM (VALUES ('early_stage', 10, NULL), "
                "('late_stage', 130, NULL), ('late_stage', 90, 'cured')) t(queue, current_dpd, outcome)")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "cache_get", lambda *a, **k: None)
    monkeypatch.setattr(llm, "cache_put", lambda *a, **k: None)
    return ask.Engine(con)


QUESTION = "Which queue has the worst average days past due once you weigh it by how long cases have been open?"


def test_slow_llm_returns_within_budget_with_closest_certified(eng, monkeypatch):
    monkeypatch.setattr(ask.Engine, "_agent", lambda self, *a: (time.sleep(3), (None, []))[1])
    t0 = time.time()
    a = eng.answer(QUESTION, budget_s=0.5)
    assert time.time() - t0 < 2                                   # never the agent's 3 s
    assert a.route == "fallback" and not a.refused
    assert "taking longer than" in a.answer and "from the cache" in a.answer
    assert a.understood_as["certified_metric"] == "average_dpd" and a.sql   # the closest certified answer, with SQL


def test_usage_limit_gives_a_clear_message(eng, monkeypatch):
    def limit(self, *a):
        raise RuntimeError("claude CLI error: Claude AI usage limit reached|1759590000")
    monkeypatch.setattr(ask.Engine, "_agent", limit)
    a = eng.answer(QUESTION, budget_s=5)
    assert a.route == "fallback" and "usage limit" in a.answer and "Traceback" not in a.answer


def test_any_failure_is_a_fallback_never_an_exception(eng, monkeypatch):
    def boom(self, *a):
        raise ValueError("bad JSON from the model")
    monkeypatch.setattr(ask.Engine, "_agent", boom)
    a = eng.answer("Which agents handled the most disputes last week?", budget_s=5)
    assert a.route == "fallback" and "could not finish" in a.answer and "explain case" in a.answer
    assert a.table is None                                        # nothing close: no unrelated numbers shown


def test_runner_mode_still_raises_so_run_benchmark_can_retry(eng, monkeypatch):
    def limit(self, *a):
        raise RuntimeError("usage limit reached")
    monkeypatch.setattr(ask.Engine, "_agent", limit)
    with pytest.raises(RuntimeError):
        eng.answer(QUESTION)                                      # budget_s=None: the benchmark path


def test_no_llm_on_the_page_is_a_fallback(eng, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    a = eng.answer(QUESTION, budget_s=5)
    assert a.route == "fallback" and "No LLM is configured" in a.answer


def test_limit_detection():
    assert ask._is_limit(RuntimeError("Claude AI usage limit reached"))
    assert ask._is_limit(RuntimeError("Error code: 429 rate_limit_error"))
    assert not ask._is_limit(ValueError("bad JSON"))
