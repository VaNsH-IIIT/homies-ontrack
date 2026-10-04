"""Committed deliverables are rewritten only on purpose (K9: a judge's run must not overwrite them)."""
import importlib

from ontrack import config


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ONTRACK_WRITE_DELIVERABLES", raising=False)
    else:
        monkeypatch.setenv("ONTRACK_WRITE_DELIVERABLES", value)
    return importlib.reload(config)


def test_default_writes_to_work_dir(monkeypatch):
    cfg = _reload(monkeypatch, None)
    out = cfg.deliverable_path("docs/data_quality_report.md")
    assert out == cfg.WORK_DIR / "outputs" / "data_quality_report.md"
    assert cfg.REPO_ROOT / "docs" not in out.parents
    assert out.parent.exists()


def test_opt_in_writes_committed_copy(monkeypatch):
    cfg = _reload(monkeypatch, "1")
    assert cfg.deliverable_path("benchmark/answers.csv") == cfg.REPO_ROOT / "benchmark" / "answers.csv"
    _reload(monkeypatch, None)
