"""Discrete-time inspection hazard (internal; never family-facing)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from models.config import AS_OF_DATE, HAZARD_MAX_WEEK, NEXT_60D_WEEKS
from models.synthetic import interval_weeks


def _pad_ccn(value: object) -> str:
    return str(value).zfill(6)


def _person_weeks(surveys: pd.DataFrame, as_of: date, max_week: int = HAZARD_MAX_WEEK) -> pd.DataFrame:
    df = surveys.copy()
    df["survey_date"] = pd.to_datetime(df["survey_date"])
    df = df.sort_values(["ccn", "survey_date"])
    rows: list[dict] = []
    as_of_ts = pd.Timestamp(as_of)
    for ccn, g in df.groupby("ccn", sort=True):
        dates = list(g["survey_date"].sort_values())
        for i, end in enumerate(dates):
            start = dates[i - 1] if i else None
            if start is None:
                continue
            lag = int(round((end - start).days / 7.0))
            if lag <= 0:
                continue
            month = int(end.month)
            for w in range(1, min(lag, max_week) + 1):
                rows.append(
                    {
                        "ccn": _pad_ccn(ccn),
                        "weeks_since_last": w,
                        "event": int(w == lag),
                        "month": month,
                    }
                )
        last = dates[-1]
        open_lag = int(round((as_of_ts - last).days / 7.0))
        for w in range(1, min(max(open_lag, 0), max_week) + 1):
            rows.append(
                {
                    "ccn": _pad_ccn(ccn),
                    "weeks_since_last": w,
                    "event": 0,
                    "month": int(as_of.month),
                }
            )
    return pd.DataFrame(rows)


def _design(weeks: np.ndarray, months: np.ndarray) -> np.ndarray:
    w = weeks.astype(float)
    m = months.astype(float)
    return np.column_stack(
        [
            w,
            w**2 / 100.0,
            (w >= 40).astype(float),
            (w >= 49).astype(float),
            (w >= 61).astype(float),
            (w >= 69).astype(float),
            np.sin(2 * np.pi * m / 12.0),
            np.cos(2 * np.pi * m / 12.0),
        ]
    )


def fit_hazard(
    surveys: pd.DataFrame,
    as_of: str | date = AS_OF_DATE,
    max_week: int = HAZARD_MAX_WEEK,
) -> tuple[np.ndarray, LogisticRegression | None]:
    """Return h[w] for w=0..max_week and the fitted logit (or None if fallback)."""
    as_of_d = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    pw = _person_weeks(surveys, as_of_d, max_week=max_week)
    if not pw.empty:
        pw = pw.sort_values(["ccn", "weeks_since_last", "event", "month"]).reset_index(drop=True)
    emp = np.zeros(max_week + 1, dtype=float)
    if pw.empty:
        emp[40:61] = 0.08
        emp[emp == 0] = 0.01
        return emp, None

    grp = pw.groupby("weeks_since_last")["event"].agg(["sum", "count"])
    prior = float(pw["event"].mean()) if len(pw) else 0.04
    prior = float(np.clip(prior, 0.01, 0.15))
    for w in range(max_week + 1):
        emp[w] = prior
    for w, row in grp.iterrows():
        wi = int(w)
        if 0 <= wi <= max_week:
            n = float(row["count"])
            k = float(row["sum"])
            raw = (k + 0.5) / (n + 1.0)
            shrink = n / (n + 25.0)
            emp[wi] = shrink * raw + (1.0 - shrink) * prior
    kernel = np.array([0.15, 0.2, 0.3, 0.2, 0.15])
    padded = np.pad(emp, 2, mode="edge")
    emp = np.convolve(padded, kernel, mode="valid")
    emp = np.clip(emp, 1e-4, 0.85)

    model = None
    try:
        x = _design(pw["weeks_since_last"].to_numpy(), pw["month"].to_numpy())
        y = pw["event"].to_numpy()
        if y.sum() >= 8 and y.sum() < len(y):
            model = LogisticRegression(max_iter=400, C=1.0, solver="lbfgs", random_state=0)
            model.fit(x, y)
            grid_w = np.arange(0, max_week + 1)
            grid_m = np.full_like(grid_w, as_of_d.month, dtype=float)
            pred = model.predict_proba(_design(grid_w, grid_m))[:, 1]
            pred = np.clip(pred, 1e-4, 0.4)
            # Logit is a smoother; keep empirical spike in 40–60 weeks.
            blend = 0.75 * emp + 0.25 * pred
            blend[70:] = emp[70:]
            emp = np.clip(blend, 1e-4, 0.85)
    except Exception:
        model = None
    emp[0] = 0.0
    return emp, model


def cumulative_p(h: np.ndarray, start_week: int, n_weeks: int = NEXT_60D_WEEKS) -> float:
    surv = 1.0
    for k in range(n_weeks):
        idx = min(start_week + k, len(h) - 1)
        surv *= 1.0 - float(h[idx])
    return float(1.0 - surv)


def current_lags(surveys: pd.DataFrame, as_of: str | date = AS_OF_DATE) -> pd.DataFrame:
    as_of_d = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    df = surveys.copy()
    df["survey_date"] = pd.to_datetime(df["survey_date"])
    last = df.groupby("ccn", as_index=False).agg(
        last_survey=("survey_date", "max"),
    )
    last["ccn"] = last["ccn"].map(_pad_ccn)
    last["weeks_since_last"] = ((pd.Timestamp(as_of_d) - last["last_survey"]).dt.days / 7.0).round().astype(int)
    last["weeks_since_last"] = last["weeks_since_last"].clip(lower=0)
    last["last_month"] = last["last_survey"].dt.month
    return last


def hazard_table(
    surveys: pd.DataFrame,
    facilities: pd.DataFrame,
    as_of: str | date = AS_OF_DATE,
    max_week: int = HAZARD_MAX_WEEK,
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    h, _model = fit_hazard(surveys, as_of=as_of, max_week=max_week)
    lags = current_lags(surveys, as_of=as_of)
    ccns = sorted(set(facilities["ccn"].map(_pad_ccn)) | set(lags["ccn"]))
    rows = []
    for ccn in ccns:
        for w in range(0, max_week + 1):
            rows.append(
                {
                    "ccn": ccn,
                    "weeks_since_last": int(w),
                    "p_survey_week": round(float(h[w]), 8),
                    "p_next_60d": round(cumulative_p(h, w), 8),
                }
            )
    table = pd.DataFrame(rows)
    return table, h, lags


def bunching_share(surveys: pd.DataFrame) -> float:
    gaps = interval_weeks(surveys)
    if gaps.empty:
        return 0.0
    return float(((gaps["weeks_since_last"] >= 40) & (gaps["weeks_since_last"] <= 60)).mean())


def gap_summary(surveys: pd.DataFrame) -> dict:
    """Completed inter-survey gaps. Georgia is late (median ~74 weeks), not NBER 74% in 40–60."""
    gaps = interval_weeks(surveys)
    if gaps.empty:
        return {"n_gaps": 0, "share_40_60": 0.0, "median_weeks": None}
    weeks = gaps["weeks_since_last"]
    return {
        "n_gaps": int(len(weeks)),
        "share_40_60": round(float(((weeks >= 40) & (weeks <= 60)).mean()), 4),
        "median_weeks": float(weeks.median()),
    }
