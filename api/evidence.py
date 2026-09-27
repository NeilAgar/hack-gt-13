"""Evidence page: the statewide event study and its placebo, computed from A's tables at request time.
Every number the page shows comes from here, so it can't drift from the data (AGENTS.md rule 7)."""
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from api import data

PAGE = Path(__file__).resolve().parent / "static" / "evidence.html"

# Days relative to the CMS Survey Date (the inspection's last day), per DECISIONS.md.
ON_SITE = (-4, -1)       # the last days before the recorded end date, when inspectors are typically on site
PRE_ARRIVAL = (-14, -5)  # the rest of the scored window, before a typical survey starts
BASELINE = (28, 56)      # a month later, as in the score


def _window(curve, lo, hi):
    vals = [p["v"] for p in curve if lo <= p["d"] <= hi and p["v"] is not None]
    return sum(vals) / len(vals) if vals else None


def _excess(curve):
    """Mean staffing in each window minus the baseline, in hours per resident day."""
    base = _window(curve, *BASELINE)
    peak = max((p for p in curve if p["v"] is not None and p["d"] < 0), key=lambda p: p["v"])
    return {
        "on_site": _window(curve, *ON_SITE) - base,
        "pre_arrival": _window(curve, *PRE_ARRIVAL) - base,
        "peak_day": peak["d"],
        "peak": peak["v"] - base,
    }


def _read_curve(path):
    import pandas as pd
    df = pd.read_parquet(path)
    df = df[df["ccn"].astype(str) == "GA"].sort_values("rel_day")
    return [{"d": int(r.rel_day), "v": float(r.hprd_resid_mean), "n": int(r.n_obs)} for r in df.itertuples()]


@lru_cache
def evidence():
    """None until A's curves, placebo and daily staffing exist."""
    p = data.PROCESSED
    paths = {k: p / f"{k}.parquet" for k in ("curves", "placebo_curve", "daily_staffing", "scores", "surveys")}
    if not all(v.exists() for v in paths.values()):
        return None
    import pandas as pd
    state, placebo = _read_curve(paths["curves"]), _read_curve(paths["placebo_curve"])
    daily = pd.read_parquet(paths["daily_staffing"], columns=["ccn", "date", "hprd"])
    scores = pd.read_parquet(paths["scores"])
    surveys = pd.read_parquet(paths["surveys"])
    mean_hprd = float(daily["hprd"].mean())
    first, last = str(daily["date"].min())[:10], str(daily["date"].max())[:10]
    in_window = surveys[(surveys["survey_date"].astype(str) >= first) & (surveys["survey_date"].astype(str) <= last)]
    real, fake = _excess(state), _excess(placebo)

    def pct(v):
        return round(100 * v / mean_hprd, 1)

    return {
        "windows": {"on_site": ON_SITE, "pre_arrival": PRE_ARRIVAL, "baseline": BASELINE},
        "state_curve": state,
        "placebo_curve": placebo,
        "mean_hprd": round(mean_hprd, 2),
        "real": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in real.items()}
        | {"on_site_pct": pct(real["on_site"]), "pre_arrival_pct": pct(real["pre_arrival"]), "peak_pct": pct(real["peak"])},
        "placebo": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in fake.items()}
        | {"on_site_pct": pct(fake["on_site"]), "pre_arrival_pct": pct(fake["pre_arrival"])},
        "sample": {
            "facilities": int(daily["ccn"].nunique()),
            "facility_days": int(len(daily)),
            "inspections": int(len(in_window)),
            "pbj_from": first,
            "pbj_to": last,
        },
        "scores": {
            "scored": int(len(scores)),
            "labels": {k: int(v) for k, v in scores["label"].value_counts().items()},
            "median_weekend_dip_pct": round(float(scores["weekend_dip_pct"].median()), 1),
        },
    }


router = APIRouter()


@router.get("/api/evidence")
def evidence_endpoint():
    ev = evidence()
    if ev is None:
        raise HTTPException(503, "Evidence needs A's processed tables (run make data)")
    return ev


@router.get("/evidence", response_class=HTMLResponse)
def evidence_page():
    return PAGE.read_text()
