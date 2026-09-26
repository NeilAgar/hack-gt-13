"""Stackelberg / ORIGAMI monthly inspection probabilities and sampler."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from models.config import (
    DEFAULT_MONTH,
    FORCED_WEEKS,
    OFF_HOURS_MIN_SHARE,
    TARGET_AVG_MONTHS,
    WEEKS_PER_MONTH,
)


def default_capacity(n_facilities: int) -> int:
    """K such that statewide mean interval stays near 12.9 months."""
    return max(1, int(round(n_facilities / TARGET_AVG_MONTHS)))


def risk_weights(facilities: pd.DataFrame, scores: pd.DataFrame) -> pd.Series:
    fac = facilities.copy()
    fac["ccn"] = fac["ccn"].astype(str).str.zfill(6)
    sc = scores.copy()
    sc["ccn"] = sc["ccn"].astype(str).str.zfill(6)
    df = fac.merge(sc, on="ccn", how="left", suffixes=("", "_s"))
    residents = pd.to_numeric(df.get("avg_residents"), errors="coerce").fillna(80.0)
    score = pd.to_numeric(df.get("score_pct"), errors="coerce").fillna(0.0).clip(lower=0)
    harm = pd.to_numeric(df.get("harm_citations_3y"), errors="coerce").fillna(0.0)
    ij = pd.to_numeric(df.get("ij_citations_3y"), errors="coerce").fillna(0.0)
    weekend = pd.to_numeric(df.get("weekend_dip_pct"), errors="coerce").fillna(0.0)
    weekend_hit = (-weekend).clip(lower=0)
    agency = pd.to_numeric(df.get("agency_share"), errors="coerce").fillna(0.0).clip(lower=0)
    risk = residents * (
        0.25 + score / 10.0 + 0.2 * harm + 0.4 * ij + weekend_hit / 20.0 + 2.0 * agency
    )
    return pd.Series(risk.to_numpy(), index=df["ccn"].to_numpy(), dtype=float)


def _try_pulp_lp(
    ccns: list[str],
    risk: np.ndarray,
    forced: np.ndarray,
    banned: np.ndarray,
    capacity: float,
) -> np.ndarray | None:
    try:
        import pulp
    except ImportError:
        return None
    n = len(ccns)
    k_eff = float(capacity)
    # Forced homes consume coverage even if K is tight (legal 15.9-month clock).
    n_forced = int(forced.sum())
    if n_forced > k_eff:
        k_eff = float(n_forced)

    prob = pulp.LpProblem("popquiz_origami", pulp.LpMinimize)
    c = [pulp.LpVariable(f"c_{i}", lowBound=0, upBound=1) for i in range(n)]
    u = pulp.LpVariable("u", lowBound=0)
    # Tie-break: cover more residual risk once attacker payoff is equalized.
    eps = 1e-4
    prob += u - eps * pulp.lpSum(float(risk[i]) * c[i] for i in range(n))
    for i in range(n):
        if banned[i]:
            prob += c[i] == 0
            continue
        if forced[i]:
            prob += c[i] == 1
            continue
        # u >= risk_i * (1 - c_i)
        prob += u + float(risk[i]) * c[i] >= float(risk[i])
    eligible = [c[i] for i in range(n) if not banned[i]]
    if eligible:
        prob += pulp.lpSum(eligible) <= k_eff
    try:
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=20))
    except Exception:
        return None
    if pulp.LpStatus[status] != "Optimal":
        return None
    out = np.zeros(n)
    for i in range(n):
        val = c[i].value()
        out[i] = 0.0 if val is None else float(val)
    return np.clip(out, 0.0, 1.0)


def _proportional_fallback(
    risk: np.ndarray,
    forced: np.ndarray,
    banned: np.ndarray,
    capacity: float,
) -> np.ndarray:
    n = len(risk)
    c = np.zeros(n)
    c[forced & ~banned] = 1.0
    used = float(c.sum())
    rem = max(0.0, float(capacity) - used)
    mask = ~forced & ~banned
    if rem <= 0 or not mask.any():
        return c
    w = np.where(mask, np.maximum(risk, 1e-6), 0.0)
    s = w.sum()
    if s <= 0:
        idx = np.flatnonzero(mask)
        share = rem / len(idx)
        c[idx] = np.minimum(1.0, share)
        return c
    raw = rem * (w / s)
    c = c + np.minimum(raw, 1.0)
    # If clipping leftover, dump onto highest-risk eligible.
    leftover = rem - float(c[mask].sum())
    if leftover > 1e-8:
        order = np.argsort(-risk)
        for i in order:
            if not mask[i] or c[i] >= 1.0:
                continue
            add = min(1.0 - c[i], leftover)
            c[i] += add
            leftover -= add
            if leftover <= 1e-8:
                break
    return np.clip(c, 0.0, 1.0)


def solve_coverage(
    ccns: list[str],
    risk: np.ndarray,
    forced: np.ndarray,
    banned: np.ndarray,
    capacity: int,
) -> tuple[np.ndarray, str]:
    lp = _try_pulp_lp(ccns, risk, forced, banned, float(capacity))
    if lp is not None:
        lp[forced & ~banned] = 1.0
        lp[banned] = 0.0
        return np.clip(lp, 0.0, 1.0), "lp"
    return _proportional_fallback(risk, forced, banned, float(capacity)), "proportional"


def sample_selected(
    ccns: list[str],
    probs: np.ndarray,
    forced: np.ndarray,
    banned: np.ndarray,
    capacity: int,
    seed: int,
) -> list[int]:
    """Systematic / weighted sample of exactly min(K, eligible) homes; forced always in."""
    rng = np.random.default_rng(seed)
    forced_idx = [i for i, f in enumerate(forced) if f and not banned[i]]
    chosen = list(forced_idx)
    k = int(capacity)
    if len(chosen) >= k:
        return chosen
    remaining_need = k - len(chosen)
    pool = [i for i in range(len(ccns)) if i not in set(chosen) and not banned[i] and probs[i] > 1e-12]
    if not pool:
        return chosen
    if remaining_need >= len(pool):
        return chosen + pool
    weights = np.array([max(probs[i], 1e-12) for i in pool], dtype=float)
    # Efraimidis–Spirakis weighted sample without replacement.
    keys = rng.random(len(pool)) ** (1.0 / weights)
    order = np.argsort(-keys)
    pick = [pool[j] for j in order[:remaining_need]]
    return chosen + pick


def mark_off_hours(n_selected: int, seed: int) -> list[bool]:
    if n_selected <= 0:
        return []
    n_off = max(1, int(np.ceil(OFF_HOURS_MIN_SHARE * n_selected)))
    n_off = min(n_off, n_selected)
    rng = np.random.default_rng(seed + 99)
    flags = [False] * n_selected
    for i in rng.choice(n_selected, size=n_off, replace=False):
        flags[int(i)] = True
    return flags


def build_schedule(
    facilities: pd.DataFrame,
    scores: pd.DataFrame,
    lags: pd.DataFrame,
    month: str = DEFAULT_MONTH,
    capacity: int | None = None,
    seed: int = 0,
) -> dict:
    month_n = int(month.split("-")[1])
    fac = facilities.copy()
    fac["ccn"] = fac["ccn"].astype(str).str.zfill(6)
    names = dict(zip(fac["ccn"], fac.get("name", fac["ccn"])))
    risk_s = risk_weights(fac, scores)
    lag_df = lags.copy()
    lag_df["ccn"] = lag_df["ccn"].astype(str).str.zfill(6)
    lag_map = dict(zip(lag_df["ccn"], lag_df["weeks_since_last"]))
    last_m = dict(zip(lag_df["ccn"], lag_df["last_month"])) if "last_month" in lag_df.columns else {}

    ccns = list(fac["ccn"])
    risk = np.array([float(risk_s.get(c, 50.0)) for c in ccns])
    weeks = np.array([int(lag_map.get(c, 20)) for c in ccns])
    forced = weeks >= FORCED_WEEKS
    banned = np.array([int(last_m.get(c, -1)) == month_n for c in ccns])
    # Cannot ban a legally forced home.
    banned = banned & ~forced

    k = int(capacity) if capacity is not None else default_capacity(len(ccns))
    k = max(k, int(forced.sum()))
    probs, method = solve_coverage(ccns, risk, forced, banned, k)
    idx = sample_selected(ccns, probs, forced, banned, k, seed)
    # Prefer higher-prob first in the published list.
    idx = sorted(idx, key=lambda i: (-probs[i], ccns[i]))
    off = mark_off_hours(len(idx), seed)

    selected = []
    for j, i in enumerate(idx):
        selected.append(
            {
                "ccn": ccns[i],
                "name": names.get(ccns[i], ccns[i]),
                "prob": round(float(probs[i]), 6),
                "forced": bool(forced[i]),
                "off_hours": bool(off[j]),
            }
        )
    probs_out = [
        {"ccn": ccns[i], "prob": round(float(probs[i]), 6), "forced": bool(forced[i])}
        for i in range(len(ccns))
    ]
    probs_out.sort(key=lambda r: (-r["prob"], r["ccn"]))
    return {
        "month": month,
        "capacity": k,
        "solver": method,
        "selected": selected,
        "probs": probs_out,
    }


def month_inspect_probs_from_plan(plan: dict) -> dict[str, float]:
    return {row["ccn"]: float(row["prob"]) for row in plan["probs"]}
