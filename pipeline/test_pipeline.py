"""Smoke test: processed Georgia tables match CONTRACTS.md."""

import pandas as pd

from pipeline.cms import (
    DAILY_STAFFING_COLS,
    FACILITIES_COLS,
    PROCESSED,
    SCORES_COLS,
    SURVEYS_COLS,
)
from pipeline.scores import format_headline
from pipeline.main import main


def _ensure_processed() -> None:
    needed = [
        PROCESSED / "facilities.parquet",
        PROCESSED / "daily_staffing.parquet",
        PROCESSED / "surveys.parquet",
        PROCESSED / "scores.parquet",
        PROCESSED / "curves.parquet",
    ]
    if not all(p.exists() for p in needed):
        main()
        return
    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    inside = (scores["ci_low"] <= scores["score_pct"]) & (scores["score_pct"] <= scores["ci_high"])
    if (not set(scores["label"].astype(str).unique()) <= {"High", "Watch", "Low"}) or (not inside.all()):
        from pipeline.scores import build_scores

        facilities = pd.read_parquet(PROCESSED / "facilities.parquet")
        daily = pd.read_parquet(PROCESSED / "daily_staffing.parquet")
        surveys = pd.read_parquet(PROCESSED / "surveys.parquet")
        build_scores(daily, surveys, facilities).to_parquet(
            PROCESSED / "scores.parquet", index=False
        )


def test_contract_tables_and_counts() -> None:
    _ensure_processed()
    facilities = pd.read_parquet(PROCESSED / "facilities.parquet")
    daily = pd.read_parquet(PROCESSED / "daily_staffing.parquet")
    surveys = pd.read_parquet(PROCESSED / "surveys.parquet")
    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    curves = pd.read_parquet(PROCESSED / "curves.parquet")

    assert list(facilities.columns) == FACILITIES_COLS
    assert list(daily.columns) == DAILY_STAFFING_COLS
    assert list(surveys.columns) == SURVEYS_COLS
    assert list(scores.columns) == SCORES_COLS

    assert facilities["ccn"].map(lambda x: isinstance(x, str) and len(x) == 6).all()
    assert daily["ccn"].map(lambda x: isinstance(x, str) and len(x) == 6).all()
    assert surveys["ccn"].map(lambda x: isinstance(x, str) and len(x) == 6).all()
    assert (surveys["survey_type"] == "health_standard").all()
    assert (surveys["source"] == "current").all()
    assert set(scores["label"].unique()) <= {"High", "Watch", "Low"}
    assert (scores.loc[scores["trophy_flag"], "ci_low"] > 0).all()
    assert (scores["ci_low"] <= scores["score_pct"]).all()
    assert (scores["score_pct"] <= scores["ci_high"]).all()
    assert (scores["ci_high"] - scores["ci_low"]).median() > 2
    sample = scores.iloc[0]
    headline = format_headline(
        sample["score_pct"], sample["ci_low"], sample["ci_high"], int(sample["n_surveys"])
    )
    assert "before" not in headline.lower()
    assert "through the last day of past inspections" in headline
    assert set(curves["ccn"].astype(str)) >= {"GA"}
    assert curves.loc[curves["ccn"] == "GA", "rel_day"].min() <= -42
    assert curves.loc[curves["ccn"] == "GA", "rel_day"].max() >= 56
    assert curves["ccn"].nunique() > 2

    n_facilities = len(facilities)
    n_surveys = len(surveys)
    print(f"GA facilities: {n_facilities}")
    print(f"GA Health Standard surveys: {n_surveys}")
    print(f"score rows: {len(scores)}")
    assert n_facilities > 300
    assert n_surveys > 500
    assert len(scores) > 50
