"""Smoke test: processed Georgia tables match CONTRACTS.md."""

import pandas as pd

from pipeline.cms import DAILY_STAFFING_COLS, FACILITIES_COLS, PROCESSED, SURVEYS_COLS
from pipeline.main import main


def _ensure_processed() -> None:
    needed = [
        PROCESSED / "facilities.parquet",
        PROCESSED / "daily_staffing.parquet",
        PROCESSED / "surveys.parquet",
    ]
    if not all(p.exists() for p in needed):
        main()


def test_contract_tables_and_counts() -> None:
    _ensure_processed()
    facilities = pd.read_parquet(PROCESSED / "facilities.parquet")
    daily = pd.read_parquet(PROCESSED / "daily_staffing.parquet")
    surveys = pd.read_parquet(PROCESSED / "surveys.parquet")

    assert list(facilities.columns) == FACILITIES_COLS
    assert list(daily.columns) == DAILY_STAFFING_COLS
    assert list(surveys.columns) == SURVEYS_COLS

    assert facilities["ccn"].map(lambda x: isinstance(x, str) and len(x) == 6).all()
    assert daily["ccn"].map(lambda x: isinstance(x, str) and len(x) == 6).all()
    assert surveys["ccn"].map(lambda x: isinstance(x, str) and len(x) == 6).all()
    assert (surveys["survey_type"] == "health_standard").all()
    assert (surveys["source"] == "current").all()

    n_facilities = len(facilities)
    n_surveys = len(surveys)
    print(f"GA facilities: {n_facilities}")
    print(f"GA Health Standard surveys: {n_surveys}")
    assert n_facilities > 300
    assert n_surveys > 500
