"""Shared paths and settings. Every module reads paths from here, never hard-coded."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = Path(os.environ.get("MAPLE_DATA_DIR", REPO_ROOT / "data" / "maple_collections_release"))
WORK_DIR = (REPO_ROOT / os.environ.get("ONTRACK_WORK_DIR", "data")).resolve()
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Committed deliverables (submission/benchmark_answers.csv, docs/data_quality_report.md) are only rewritten on purpose:
# ONTRACK_WRITE_DELIVERABLES=1 (run_all --update-deliverables). Otherwise outputs go to WORK_DIR/outputs, so a
# run on a sample or without an LLM never overwrites the submitted files in a clone.
WRITE_DELIVERABLES = os.environ.get("ONTRACK_WRITE_DELIVERABLES") == "1"


def deliverable_path(repo_relative: str) -> Path:
    """Where a committed deliverable is written: the repo copy only when WRITE_DELIVERABLES is set."""
    if WRITE_DELIVERABLES:
        return REPO_ROOT / repo_relative
    out = WORK_DIR / "outputs" / Path(repo_relative).name
    out.parent.mkdir(parents=True, exist_ok=True)
    return out

SNAPSHOT_DATE = "2026-09-28"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# The 12 columns the data dictionary tags as protected, plus age. Never used in features or decisions.
PROTECTED_COLUMNS = frozenset({
    "gender_code", "marital_status", "citizenship_status", "household_size", "dependants_count",
    "newcomer_program_flag", "newcomer_arrival_date", "accessibility_needs_flag", "accessibility_type",
    "vulnerability_type", "ccb_deposit_flag", "customer_accent_region", "age",
})
