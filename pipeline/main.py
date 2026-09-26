"""`python -m pipeline` / `make data` entrypoint."""

from __future__ import annotations

import pandas as pd

from pipeline.cms import PROCESSED
from pipeline.scores import build_scores, placebo_surveys, plot_curve
from pipeline.tables import (
    build_daily_staffing,
    build_facilities,
    build_facility_curves,
    build_state_curve,
    build_surveys,
)


def write_parquet(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"wrote {path} rows={len(df)} cols={list(df.columns)}")


def main(latest_quarter_only: bool = False) -> dict:
    from pipeline.cms import ensure_raw

    paths = ensure_raw(latest_quarter_only=latest_quarter_only)
    facilities = build_facilities(paths["providers"], paths["citations"])
    surveys = build_surveys(paths["surveys"], facilities["ccn"])
    daily = build_daily_staffing(paths["pbj"])

    write_parquet(facilities, PROCESSED / "facilities.parquet")
    write_parquet(daily, PROCESSED / "daily_staffing.parquet")
    write_parquet(surveys, PROCESSED / "surveys.parquet")

    print("--- event study (Chen & Dillender: day 0 = inspection END) ---")
    ga_curve = build_state_curve(daily, surveys)
    fac_curves = build_facility_curves(daily, surveys)
    curves = pd.concat([ga_curve, fac_curves], ignore_index=True)
    write_parquet(curves, PROCESSED / "curves.parquet")
    plot_curve(
        ga_curve,
        PROCESSED / "ga_state_curve.png",
        "GA state-average staffing residual (day 0 = inspection end)",
        "CMS Survey Date (exit)",
    )

    print("--- scores ---")
    scores = build_scores(daily, surveys, facilities)
    write_parquet(scores, PROCESSED / "scores.parquet")

    print("--- placebo (random fake survey dates) ---")
    fake = placebo_surveys(daily, surveys)
    placebo_curve = build_state_curve(daily, fake)
    write_parquet(placebo_curve, PROCESSED / "placebo_curve.parquet")
    plot_curve(
        placebo_curve,
        PROCESSED / "ga_placebo_curve.png",
        "Placebo: random fake survey dates (should have no inspection spike)",
        "fake date",
    )

    print(f"GA facilities: {len(facilities)}")
    print(f"GA Health Standard surveys: {len(surveys)}")
    print(f"curve rows: {len(curves)} (GA={len(ga_curve)} facility={len(fac_curves)})")
    return {"n_facilities": int(len(facilities)), "n_surveys": int(len(surveys))}


if __name__ == "__main__":
    main()
