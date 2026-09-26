"""Synthetic Georgia-like surveys, facilities, and scores for fixture-first builds."""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from models.config import (
    AS_OF_DATE,
    FIXTURES_DIR,
    FORCED_WEEKS,
    SYNTHETIC_N_HOMES,
    SYNTHETIC_SEED,
)

FIXTURE_LAGS = {
    # Week lags chosen so current p_next_60d ranks similarly to fixtures/predictability.json
    "115999": 72,  # overdue / forced
    "115998": 12,
    "115997": 52,
    "115996": 45,
    "115995": 8,
    "115994": 30,
}


def _pad_ccn(value: object) -> str:
    return str(value).zfill(6)


def load_fixture_facilities() -> pd.DataFrame:
    path = FIXTURES_DIR / "facilities.json"
    if not path.exists():
        return pd.DataFrame()
    rows = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


def _draw_lag_weeks(rng: np.random.Generator, size: int) -> np.ndarray:
    """Synthetic only: ~74% of intervals in 40–60 weeks (NBER national pattern)."""
    u = rng.random(size)
    lags = np.empty(size, dtype=int)
    n74 = u < 0.74
    n20 = (u >= 0.74) & (u < 0.94)
    lags[n74] = rng.integers(40, 61, size=int(n74.sum()))
    lags[n20] = rng.integers(61, 81, size=int(n20.sum()))
    rest = ~(n74 | n20)
    lags[rest] = rng.integers(18, 40, size=int(rest.sum()))
    return lags


def build_synthetic(n_homes: int = SYNTHETIC_N_HOMES, seed: int = SYNTHETIC_SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    as_of = date.fromisoformat(AS_OF_DATE)
    fixture_fac = load_fixture_facilities()

    rows_fac: list[dict] = []
    scores_rows: list[dict] = []
    survey_rows: list[dict] = []

    fixture_ccns = set()
    if not fixture_fac.empty:
        for rec in fixture_fac.to_dict(orient="records"):
            ccn = _pad_ccn(rec["ccn"])
            fixture_ccns.add(ccn)
            residents = float(70 + (int(ccn) % 80))
            score = float(rec.get("score_pct", 0.0))
            rows_fac.append(
                {
                    "ccn": ccn,
                    "name": rec["name"],
                    "city": rec.get("city", "Atlanta"),
                    "county": "Chatham" if rec.get("city") == "Savannah" else "Fulton",
                    "lat": rec.get("lat"),
                    "lon": rec.get("lon"),
                    "certified_beds": int(residents + 10),
                    "avg_residents": residents,
                    "ownership": "For profit",
                    "overall_star": int(rec.get("overall_star", 3)),
                    "staffing_star": int(rec.get("staffing_star", 3)),
                    "health_star": 3,
                    "harm_citations_3y": 2 if score >= 7 else 0,
                    "ij_citations_3y": 0,
                    "rbs_proxy_eligible": bool(rec.get("trophy_flag", False)),
                }
            )
            scores_rows.append(
                {
                    "ccn": ccn,
                    "n_surveys": 5,
                    "raw_pct": score,
                    "score_pct": score,
                    "ci_low": rec.get("ci_low", score - 3),
                    "ci_high": rec.get("ci_high", score + 3),
                    "surge_pct": max(score, 0) + 4,
                    "weekend_dip_pct": -4.0 if score >= 5 else -1.0,
                    "agency_share": 0.22 if score >= 7 else 0.08,
                    "label": rec.get("label", "Watch"),
                    "trophy_flag": bool(rec.get("trophy_flag", False)),
                }
            )

    extra_needed = max(0, n_homes - len(rows_fac))
    made = 0
    i = 0
    while made < extra_needed:
        ccn = _pad_ccn(110000 + i)
        i += 1
        if ccn in fixture_ccns:
            continue
        made += 1
        residents = float(rng.integers(40, 180))
        score = float(np.clip(rng.normal(3.0, 4.5), -6, 18))
        harm = int(rng.integers(0, 4))
        rows_fac.append(
            {
                "ccn": ccn,
                "name": f"Sample GA Home {ccn}",
                "city": rng.choice(["Atlanta", "Savannah", "Augusta", "Macon", "Columbus"]),
                "county": "Synthetic",
                "lat": 33.0 + rng.normal(0, 0.4),
                "lon": -83.5 + rng.normal(0, 0.5),
                "certified_beds": int(residents + rng.integers(5, 25)),
                "avg_residents": residents,
                "ownership": rng.choice(["For profit", "Non profit", "Government"]),
                "overall_star": int(rng.integers(1, 6)),
                "staffing_star": int(rng.integers(1, 6)),
                "health_star": int(rng.integers(1, 6)),
                "harm_citations_3y": harm,
                "ij_citations_3y": int(rng.random() < 0.05),
                "rbs_proxy_eligible": bool(score > 0 and rng.random() < 0.15),
            }
        )
        scores_rows.append(
            {
                "ccn": ccn,
                "n_surveys": int(rng.integers(3, 8)),
                "raw_pct": score,
                "score_pct": score,
                "ci_low": score - abs(rng.normal(3, 1)),
                "ci_high": score + abs(rng.normal(3, 1)),
                "surge_pct": max(score, 0) + float(rng.uniform(0, 6)),
                "weekend_dip_pct": float(rng.uniform(-12, 2)),
                "agency_share": float(np.clip(rng.beta(2, 10), 0, 0.6)),
                "label": "Low" if score >= 6 else ("Watch" if score >= 1.5 else "High"),
                "trophy_flag": False,
            }
        )

    facilities = pd.DataFrame(rows_fac)
    scores = pd.DataFrame(scores_rows)

    for rec in facilities.itertuples(index=False):
        ccn = rec.ccn
        n_hist = 5
        lags = _draw_lag_weeks(rng, n_hist)
        if ccn in FIXTURE_LAGS:
            current_lag = FIXTURE_LAGS[ccn]
        else:
            current_lag = int(_draw_lag_weeks(rng, 1)[0])
            if current_lag >= int(FORCED_WEEKS):
                current_lag = int(rng.integers(28, 58))
            roll = rng.random()
            if roll < 0.025:
                current_lag = int(FORCED_WEEKS) + int(rng.integers(0, 8))
            elif roll < 0.14:
                # Same calendar month as as_of (scheduler must ban unless forced).
                prior = date(as_of.year - 1, as_of.month, min(as_of.day, 28))
                current_lag = max(1, int(round((as_of - prior).days / 7.0)))

        cursor = as_of - timedelta(weeks=int(current_lag))
        dates = [cursor]
        for lag in lags:
            cursor = cursor - timedelta(weeks=int(lag))
            dates.append(cursor)
        for d in sorted(dates):
            if d >= as_of:
                continue
            survey_rows.append(
                {
                    "ccn": ccn,
                    "survey_date": d.isoformat(),
                    "survey_type": "health_standard",
                    "source": "archive" if d.year < 2023 else "current",
                }
            )

    surveys = pd.DataFrame(survey_rows)
    surveys["ccn"] = surveys["ccn"].map(_pad_ccn)
    return {"facilities": facilities, "scores": scores, "surveys": surveys}


def interval_weeks(surveys: pd.DataFrame) -> pd.DataFrame:
    """Completed inter-survey gaps (weeks) for sanity checks and hazard training."""
    df = surveys.copy()
    df["survey_date"] = pd.to_datetime(df["survey_date"])
    df = df.sort_values(["ccn", "survey_date"])
    df["prev"] = df.groupby("ccn")["survey_date"].shift(1)
    gaps = df.dropna(subset=["prev"]).copy()
    gaps["weeks_since_last"] = ((gaps["survey_date"] - gaps["prev"]).dt.days / 7.0).round().astype(int)
    return gaps[gaps["weeks_since_last"] > 0]
