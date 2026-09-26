"""Constants for the hazard, scheduler, and simulation modules."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
FIXTURES_DIR = ROOT / "fixtures"

# CMS "must inspect by" clock and statewide average (architecture §4).
FORCED_MONTHS = 15.9
TARGET_AVG_MONTHS = 12.9
WEEKS_PER_MONTH = 365.25 / 12.0 / 7.0  # ~4.345
FORCED_WEEKS = FORCED_MONTHS * WEEKS_PER_MONTH  # ~69.1
OFF_HOURS_MIN_SHARE = 0.10

HAZARD_MAX_WEEK = 90
NEXT_60D_WEEKS = 9  # 9*7 = 63 days, contract's p_next_60d
SIM_MONTHS = 36

# Snapshot date of A's Inspection Dates file (NH_SurveyDates_Aug2026).
# Do not use a future as-of; that inflates the 15.9-month overdue count.
DEFAULT_MONTH = "2026-08"
AS_OF_DATE = "2026-07-31"
SYNTHETIC_N_HOMES = 80
SYNTHETIC_SEED = 13
