"""Each home's "normal day" line for the staffing chart: the 95th percentile of its own staffing on ordinary
days, on the same scale as its curve. A spike above it is unusual for this home, not just for Georgia.

Choices (see README.md, "The normal-day line on the chart"):
- Ordinary days are more than 60 days from any of the home's inspections; the chart spans days -42..+56.
- A curve point averages that day across the home's inspections, so the line is the 95th percentile of the
  average of that many random ordinary days (an average of 2 days swings less than 1 day).
- Fixed seed per home, so the line never moves between runs.
"""
import numpy as np

EXCLUDE_DAYS = 60   # beyond the chart's widest window (+56), so no inspection-affected day counts as ordinary
MIN_DAYS = 60       # fewer ordinary days than this and the percentile isn't stable enough to draw
DRAWS = 5000
PERCENTILE = 95


def _seed(ccn):
    return int(ccn, 36)  # CCNs are 6 alphanumeric characters; stable across runs


def normal_p95(dates, values, survey_dates, n_inspections, ccn):
    """(p95, n_ordinary_days); p95 is None when there aren't enough ordinary days."""
    dates = np.asarray(dates, dtype="datetime64[D]")
    values = np.asarray(values, dtype=float)
    keep = ~np.isnan(values)
    for s in survey_dates:
        keep &= np.abs((dates - np.datetime64(s, "D")).astype(int)) > EXCLUDE_DAYS
    pool = values[keep]
    if len(pool) < MIN_DAYS or not n_inspections:
        return None, int(len(pool))
    rng = np.random.default_rng(_seed(ccn))
    draws = pool[rng.integers(0, len(pool), size=(DRAWS, int(n_inspections)))].mean(axis=1)
    return round(float(np.percentile(draws, PERCENTILE)), 4), int(len(pool))


def all_homes(processed_dir, curves):
    """{ccn: (p95, n_ordinary_days)} for every home with a curve. curves: the per-home rows of curves.parquet."""
    import pandas as pd
    daily_path, surveys_path = processed_dir / "daily_staffing.parquet", processed_dir / "surveys.parquet"
    if not (daily_path.exists() and surveys_path.exists()):
        return {}
    daily = pd.read_parquet(daily_path, columns=["ccn", "date", "hprd_resid"])
    daily["ccn"] = daily["ccn"].astype(str).str.zfill(6)
    surveys = pd.read_parquet(surveys_path, columns=["ccn", "survey_date"])
    surveys["ccn"] = surveys["ccn"].astype(str).str.zfill(6)
    by_home = surveys.groupby("ccn")["survey_date"].apply(list).to_dict()
    k = curves.groupby("ccn")["n_obs"].max().to_dict()
    return {ccn: normal_p95(g["date"].astype(str).to_numpy(), g["hprd_resid"].to_numpy(),
                            [str(s)[:10] for s in by_home.get(ccn, [])], k[ccn], ccn)
            for ccn, g in daily.groupby("ccn") if ccn in k}
