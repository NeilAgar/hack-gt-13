"""Map live CMS headers onto CONTRACTS.md parquet tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipeline.cms import (
    CURVES_COLS,
    DAILY_STAFFING_COLS,
    FACILITIES_COLS,
    HD_CCN,
    HD_SCOPE,
    HD_STATE,
    HARM_CODES,
    HRS_CNA,
    HRS_CONTRACT,
    HRS_LPN,
    HRS_RN,
    IJ_CODES,
    PI_AVG_RES,
    PI_BEDS,
    PI_CCN,
    PI_CITY,
    PI_COUNTY,
    PI_HEALTH,
    PI_LAT,
    PI_LON,
    PI_NAME,
    PI_OVERALL,
    PI_OWNERSHIP,
    PI_STAFFING,
    PI_STATE,
    SURVEY_CCN,
    SURVEY_DATE,
    SURVEY_TYPE,
    SURVEY_TYPE_HEALTH_STANDARD,
    SURVEYS_COLS,
    pad_ccn,
)


def _to_ccn(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.zfill(6)


def _to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("float64")


def build_facilities(provider_path: Path, citations_path: Path) -> pd.DataFrame:
    info = pd.read_csv(provider_path, dtype=str, encoding="utf-8-sig", low_memory=False)
    ga = info.loc[info[PI_STATE] == "GA"].copy()
    citations = pd.read_csv(
        citations_path,
        dtype=str,
        encoding="utf-8-sig",
        usecols=[HD_CCN, HD_STATE, HD_SCOPE],
        low_memory=False,
    )
    cit_ga = citations.loc[citations[HD_STATE] == "GA"].copy()
    cit_ga["ccn"] = _to_ccn(cit_ga[HD_CCN])
    cit_ga["scope"] = cit_ga[HD_SCOPE].astype("string").str.strip().str.upper()
    harm = cit_ga.loc[cit_ga["scope"].isin(HARM_CODES)].groupby("ccn").size()
    ij = cit_ga.loc[cit_ga["scope"].isin(IJ_CODES)].groupby("ccn").size()

    out = pd.DataFrame(
        {
            "ccn": _to_ccn(ga[PI_CCN]),
            "name": ga[PI_NAME].astype("string").str.strip(),
            "city": ga[PI_CITY].astype("string").str.strip(),
            "county": ga[PI_COUNTY].astype("string").str.strip(),
            "lat": _to_float(ga[PI_LAT]),
            "lon": _to_float(ga[PI_LON]),
            "certified_beds": _to_int(ga[PI_BEDS]),
            "avg_residents": _to_float(ga[PI_AVG_RES]),
            "ownership": ga[PI_OWNERSHIP].astype("string").str.strip(),
            "overall_star": _to_int(ga[PI_OVERALL]),
            "staffing_star": _to_int(ga[PI_STAFFING]),
            "health_star": _to_int(ga[PI_HEALTH]),
        }
    )
    out["harm_citations_3y"] = out["ccn"].map(harm).fillna(0).astype("int64")
    out["ij_citations_3y"] = out["ccn"].map(ij).fillna(0).astype("int64")
    out["rbs_proxy_eligible"] = (
        (out["overall_star"] == 5)
        & (out["staffing_star"] >= 3)
        & (out["harm_citations_3y"] == 0)
        & (out["ij_citations_3y"] == 0)
    ).fillna(False).astype(bool)
    out = out.drop_duplicates(subset=["ccn"], keep="first")
    return out[FACILITIES_COLS]


def build_surveys(survey_path: Path, ga_ccns: pd.Series) -> pd.DataFrame:
    raw = pd.read_csv(survey_path, dtype=str, encoding="utf-8-sig", low_memory=False)
    raw["ccn"] = _to_ccn(raw[SURVEY_CCN])
    ga = raw.loc[raw["ccn"].isin(set(ga_ccns.astype(str)))].copy()
    # Keep only Health Inspection Standard surveys; live CMS value is "Health Standard".
    std = ga.loc[ga[SURVEY_TYPE] == SURVEY_TYPE_HEALTH_STANDARD].copy()
    std["survey_date"] = pd.to_datetime(std[SURVEY_DATE], errors="coerce").dt.strftime("%Y-%m-%d")
    std["survey_type"] = "health_standard"
    std["source"] = "current"
    std = std.dropna(subset=["survey_date"])
    std = std.drop_duplicates(subset=["ccn", "survey_date"], keep="first")
    return std[SURVEYS_COLS]


def _load_pbj(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False)
        missing = [c for c in ["PROVNUM", "WorkDate", "MDScensus", *HRS_RN, *HRS_LPN, *HRS_CNA, *HRS_CONTRACT] if c not in df.columns]
        if missing:
            raise ValueError(f"{path.name} missing headers {missing}; refusing to invent columns")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build_daily_staffing(pbj_paths: list[Path]) -> pd.DataFrame:
    raw = _load_pbj(pbj_paths)
    raw = raw.loc[raw["STATE"] == "GA"].copy()
    out = pd.DataFrame(
        {
            "ccn": _to_ccn(raw["PROVNUM"]),
            "date": pd.to_datetime(raw["WorkDate"], format="%Y%m%d", errors="coerce"),
            "census": _to_int(raw["MDScensus"]),
            "hrs_rn": sum(_to_float(raw[c]) for c in HRS_RN),
            "hrs_lpn": sum(_to_float(raw[c]) for c in HRS_LPN),
            "hrs_cna": sum(_to_float(raw[c]) for c in HRS_CNA),
            "hrs_contract": sum(_to_float(raw[c]) for c in HRS_CONTRACT),
        }
    )
    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    census = pd.to_numeric(out["census"], errors="coerce")
    hours = out["hrs_rn"] + out["hrs_lpn"] + out["hrs_cna"]
    out["hprd"] = hours / census.where(census > 0)
    out = out.sort_values(["ccn", "date"]).drop_duplicates(subset=["ccn", "date"], keep="last")
    dt = pd.to_datetime(out["date"])
    out["dow"] = dt.dt.dayofweek
    # Chen & Dillender (w34037) eq. (1): residualize with nursing-home × day-of-week
    # and nursing-home × month (year-month nests year). Contract also requires a
    # local trend; 90-day rolling mean of the two-way residual is that trend.
    out["year_month"] = dt.dt.to_period("M").astype(str)
    out["dow_mean"] = out.groupby(["ccn", "dow"], observed=True)["hprd"].transform("mean")
    out["ym_mean"] = out.groupby(["ccn", "year_month"], observed=True)["hprd"].transform("mean")
    out["ccn_mean"] = out.groupby("ccn", observed=True)["hprd"].transform("mean")
    out["hprd_fe"] = out["hprd"] - out["dow_mean"] - out["ym_mean"] + out["ccn_mean"]
    out["trend"] = (
        out.groupby("ccn", observed=True)["hprd_fe"]
        .transform(lambda s: s.rolling(window=90, min_periods=14).mean())
    )
    out["hprd_resid"] = out["hprd_fe"] - out["trend"]
    out["census"] = out["census"].astype("Int64")
    return out[DAILY_STAFFING_COLS]


def drop_overlapping_surveys(surveys: pd.DataFrame, min_gap_days: int = 150) -> pd.DataFrame:
    """Chen & Dillender: drop inspections that have another inspection within 150 days."""
    svy = surveys.copy()
    svy["survey_date"] = pd.to_datetime(svy["survey_date"])
    svy = svy.sort_values(["ccn", "survey_date"])
    svy["gap_prev"] = svy.groupby("ccn")["survey_date"].diff().dt.days
    svy["gap_next"] = svy.groupby("ccn")["survey_date"].diff(-1).dt.days.abs()
    keep = svy["gap_prev"].isna() | (svy["gap_prev"] >= min_gap_days)
    keep &= svy["gap_next"].isna() | (svy["gap_next"] >= min_gap_days)
    out = svy.loc[keep].copy()
    out["survey_date"] = out["survey_date"].dt.strftime("%Y-%m-%d")
    dropped = len(surveys) - len(out)
    print(f"overlap filter ({min_gap_days}d): kept {len(out)} / {len(surveys)} surveys (dropped {dropped})")
    return out


def event_panel(daily: pd.DataFrame, surveys: pd.DataFrame) -> pd.DataFrame:
    """Facility-day × survey, rel_day vs inspection END (CMS Survey Date)."""
    staff = daily.copy()
    staff["date"] = pd.to_datetime(staff["date"])
    svy = surveys.copy()
    svy["survey_date"] = pd.to_datetime(svy["survey_date"])
    merged = staff.merge(svy[["ccn", "survey_date"]], on="ccn", how="inner")
    merged["rel_day"] = (merged["date"] - merged["survey_date"]).dt.days
    return merged


def aggregate_curve(panel: pd.DataFrame, ccn_value: str | None = None) -> pd.DataFrame:
    from pipeline.cms import CURVE_WINDOW

    lo, hi = CURVE_WINDOW
    window = panel.loc[panel["rel_day"].between(lo, hi)].dropna(subset=["hprd_resid"])
    if ccn_value is None:
        grouped = (
            window.groupby(["ccn", "rel_day"], as_index=False)
            .agg(hprd_resid_mean=("hprd_resid", "mean"), n_obs=("hprd_resid", "size"))
        )
    else:
        grouped = (
            window.groupby("rel_day", as_index=False)
            .agg(hprd_resid_mean=("hprd_resid", "mean"), n_obs=("hprd_resid", "size"))
        )
        grouped.insert(0, "ccn", ccn_value)
    grouped["rel_day"] = grouped["rel_day"].astype("int64")
    return grouped[CURVES_COLS]


def build_state_curve(daily: pd.DataFrame, surveys: pd.DataFrame) -> pd.DataFrame:
    return aggregate_curve(event_panel(daily, surveys), ccn_value="GA")


def build_facility_curves(daily: pd.DataFrame, surveys: pd.DataFrame) -> pd.DataFrame:
    return aggregate_curve(event_panel(daily, surveys), ccn_value=None)
