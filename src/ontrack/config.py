"""Shared paths and settings. Every module reads paths from here, never hard-coded."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = Path(os.environ.get("MAPLE_DATA_DIR", REPO_ROOT / "data" / "maple_collections_release"))
WORK_DIR = (REPO_ROOT / os.environ.get("ONTRACK_WORK_DIR", "data")).resolve()
WORK_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT_DATE = "2026-09-28"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# The 12 columns the data dictionary tags as protected, plus age. Never used in features or decisions.
PROTECTED_COLUMNS = frozenset({
    "gender_code", "marital_status", "citizenship_status", "household_size", "dependants_count",
    "newcomer_program_flag", "newcomer_arrival_date", "accessibility_needs_flag", "accessibility_type",
    "vulnerability_type", "ccb_deposit_flag", "customer_accent_region", "age",
})
