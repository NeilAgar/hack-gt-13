"""Illustrative 36-month undetected-shirk comparison (status quo vs StaffTrace)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.config import AS_OF_DATE, DEFAULT_MONTH, FORCED_WEEKS, SIM_MONTHS, WEEKS_PER_MONTH
from models.hazard import current_lags
from models.scheduler import build_schedule, default_capacity, risk_weights, sample_selected


def add_month(month: str, steps: int) -> str:
    y, m = map(int, month.split("-"))
    tot = y * 12 + (m - 1) + steps
    ny, nm = divmod(tot, 12)
    return f"{ny:04d}-{nm + 1:02d}"


def _shirk_intensity(p_inspect: float) -> float:
    """Homes cut staff more when they believe inspection risk is low."""
    return float(max(0.0, 1.0 - p_inspect))


def _status_quo_belief(weeks_since: int) -> float:
    """What homes think under the historical 9–15 month window (illustrative)."""
    w = int(weeks_since)
    if w >= int(FORCED_WEEKS):
        return 0.95
    if 40 <= w <= 60:
        return 0.50
    if 35 <= w <= 65:
        return 0.18
    return 0.05


def _status_quo_actual(weeks_since: int) -> float:
    """Historical inspectors still bunch in the 40–60 week window."""
    w = int(weeks_since)
    if w >= int(FORCED_WEEKS):
        return 0.95
    if 40 <= w <= 60:
        return 0.62
    return 0.02


def simulate(
    facilities: pd.DataFrame,
    scores: pd.DataFrame,
    surveys: pd.DataFrame,
    h: np.ndarray,
    month: str = DEFAULT_MONTH,
    capacity: int | None = None,
    horizon: int = SIM_MONTHS,
    seed: int = 7,
    as_of: str = AS_OF_DATE,
) -> dict:
    """Resident-weighted undetected shirk-months; same inspector budget both arms."""
    fac = facilities.copy()
    fac["ccn"] = fac["ccn"].astype(str).str.zfill(6)
    ccns = list(fac["ccn"])
    n = len(ccns)
    _ = h
    k = int(capacity) if capacity is not None else default_capacity(n)
    k = max(1, k)

    # Harm weight per missed month: the home's standing risk, without the time term (T), which changes every
    # simulated month. The StaffTrace arm's schedule itself uses T through build_schedule's lags.
    risk_s = risk_weights(fac, scores)
    risk = np.array([float(risk_s.get(c, 50.0)) for c in ccns])
    residents = pd.to_numeric(fac.set_index("ccn").reindex(ccns)["avg_residents"], errors="coerce").fillna(80.0).to_numpy()

    lags0 = current_lags(surveys, as_of=as_of)
    lag_map = dict(zip(lags0["ccn"], lags0["weeks_since_last"]))
    last_m_map = dict(zip(lags0["ccn"], lags0["last_month"]))
    weeks = np.array([int(lag_map.get(c, 20)) for c in ccns], dtype=float)
    last_month = np.array([int(last_m_map.get(c, 1)) for c in ccns], dtype=int)

    def run(arm: str) -> float:
        w = weeks.copy()
        lm = last_month.copy()
        undetected = 0.0
        for t in range(horizon):
            ym = add_month(month, t)
            month_n = int(ym.split("-")[1])
            lag_df = pd.DataFrame(
                {
                    "ccn": ccns,
                    "weeks_since_last": np.maximum(w, 0).astype(int),
                    "last_month": lm,
                }
            )
            if arm == "popquiz":
                plan = build_schedule(fac, scores, lag_df, month=ym, capacity=k, seed=seed + t)
                selected = {row["ccn"] for row in plan["selected"]}
                actual = np.array([1.0 if c in selected else 0.0 for c in ccns])
            else:
                weights = np.array([_status_quo_actual(int(max(wi, 0))) for wi in w])
                forced = w >= FORCED_WEEKS
                banned = (lm == month_n) & (~forced)
                idx = sample_selected(ccns, weights, forced, banned, k, seed + t)
                actual = np.zeros(n, dtype=float)
                actual[idx] = 1.0

            # Short-run: homes still staff to the historical window; only the inspect process changes.
            shirk = np.array([_shirk_intensity(_status_quo_belief(int(max(wi, 0)))) for wi in w])
            missed_shirk = shirk * (1.0 - actual)
            undetected += float((residents * (risk / (risk.mean() + 1e-9)) * missed_shirk).sum())
            inspected = actual > 0.5

            w = w + WEEKS_PER_MONTH
            w[inspected] = 0.0
            lm[inspected] = month_n
        return undetected

    sq = run("status_quo")
    pq = run("popquiz")
    reduction = 0.0 if sq <= 0 else 100.0 * (sq - pq) / sq
    return {
        "months": horizon,
        "capacity": k,
        "illustrative": True,
        "status_quo": {"undetected_shirk_resident_months": round(sq, 1)},
        "popquiz": {"undetected_shirk_resident_months": round(pq, 1)},
        "reduction_pct": round(reduction, 1),
        "note": (
            "Illustrative model. Homes still staff to the historical 40-60 week window; "
            "only the inspection process changes (status quo bunches there, StaffTrace samples "
            "K risk-weighted slots). Chen & Dillender (NBER w34037); "
            "Gandhi, Olenski & Shi (NBER w34491). Does not estimate lives saved."
        ),
    }
