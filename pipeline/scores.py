"""Survey-responsiveness scores (Chen & Dillender w34037, mapped onto CONTRACTS.md).

Day 0 is the inspection END date (CMS Survey Date). Paper §3.1 / eq. (1):
inspectors must report end dates; start dates are unreliable, so they do not
shift the event study to start. Peak staffing is on day −1; hours collapse on +1.

Windows (ARCHITECTURE §2, applied on that exit-day calendar):
  pre-ramp −14..−1, surge 0..+3 (reported, not scored), baseline +28..+56.
Raw score = mean over inspections of (pre − base) / base × 100.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.cms import (
    BASELINE,
    BOOTSTRAP_REPS,
    BOOTSTRAP_SEED,
    LABEL_PLACEHOLDER,
    OVERLAP_DAYS,
    PRE_RAMP,
    PROCESSED,
    SCORES_COLS,
    SURGE,
)
from pipeline.tables import drop_overlapping_surveys, event_panel


def _window_mean(panel: pd.DataFrame, lo: int, hi: int, value_col: str) -> pd.Series:
    sub = panel.loc[panel["rel_day"].between(lo, hi) & panel[value_col].notna()]
    return sub.groupby(["ccn", "survey_date"])[value_col].mean()


def inspection_contrasts(daily: pd.DataFrame, surveys: pd.DataFrame) -> pd.DataFrame:
    svy = drop_overlapping_surveys(surveys, OVERLAP_DAYS)
    panel = event_panel(daily, svy)
    pre_h = _window_mean(panel, *PRE_RAMP, "hprd")
    base_h = _window_mean(panel, *BASELINE, "hprd")
    surge_h = _window_mean(panel, *SURGE, "hprd")
    pre_n = (
        panel.loc[panel["rel_day"].between(*PRE_RAMP) & panel["hprd"].notna()]
        .groupby(["ccn", "survey_date"])
        .size()
    )
    base_n = (
        panel.loc[panel["rel_day"].between(*BASELINE) & panel["hprd"].notna()]
        .groupby(["ccn", "survey_date"])
        .size()
    )
    out = pd.concat(
        {
            "pre_hprd": pre_h,
            "base_hprd": base_h,
            "surge_hprd": surge_h,
            "pre_n": pre_n,
            "base_n": base_n,
        },
        axis=1,
    ).reset_index()
    # Need enough days in both scored windows (pre 14 days, baseline 29 days).
    usable = out["pre_n"].fillna(0).ge(7) & out["base_n"].fillna(0).ge(14) & out["base_hprd"].gt(0)
    out = out.loc[usable].copy()
    out["raw_pct"] = (out["pre_hprd"] - out["base_hprd"]) / out["base_hprd"] * 100.0
    out["surge_pct"] = (out["surge_hprd"] - out["base_hprd"]) / out["base_hprd"] * 100.0
    print(f"usable inspections for scores: {len(out)}")
    return out


def weekend_dip(daily: pd.DataFrame) -> pd.Series:
    d = daily.dropna(subset=["hprd"]).copy()
    d["dow"] = pd.to_datetime(d["date"]).dt.dayofweek
    d["is_weekend"] = d["dow"].isin([5, 6])
    means = d.groupby(["ccn", "is_weekend"])["hprd"].mean().unstack("is_weekend")
    if True not in means.columns or False not in means.columns:
        return pd.Series(dtype="float64")
    weekday = means[False]
    weekend = means[True]
    return ((weekday - weekend) / weekday.replace(0, np.nan) * 100.0).rename("weekend_dip_pct")


def _bootstrap_ci(
    values: np.ndarray, rng: np.random.Generator, reps: int, pooled_sd: float
) -> tuple[float, float]:
    if len(values) == 0:
        return (np.nan, np.nan)
    if len(values) == 1:
        se = pooled_sd
        v = float(values[0])
        return (v - 1.96 * se, v + 1.96 * se)
    draws = rng.choice(values, size=(reps, len(values)), replace=True).mean(axis=1)
    return (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))


def empirical_bayes(raw: pd.Series, sigma2: pd.Series) -> pd.Series:
    state_mean = float(raw.mean())
    tau2 = float(max(0.0, raw.var(ddof=1) - sigma2.mean()))
    w = tau2 / (tau2 + sigma2)
    w = w.fillna(0.0)
    print(f"EB tau2={tau2:.4f} state_mean_raw={state_mean:.3f}%")
    return w * raw + (1.0 - w) * state_mean


def build_scores(daily: pd.DataFrame, surveys: pd.DataFrame, facilities: pd.DataFrame) -> pd.DataFrame:
    insp = inspection_contrasts(daily, surveys)
    counts = insp.groupby("ccn").size()
    n1 = int((counts == 1).sum())
    n2 = int((counts == 2).sum())
    n3 = int((counts >= 3).sum())
    print(f"homes with usable inspections: 1={n1}  2={n2}  3+={n3}")

    grouped = insp.groupby("ccn")
    raw = grouped["raw_pct"].mean()
    surge = grouped["surge_pct"].mean()
    n_surveys = grouped.size().astype("int64")
    # Sampling variance of the facility mean; n=1 uses pooled within-facility variance.
    within = grouped["raw_pct"].var(ddof=1)
    pooled = float(within.dropna().mean()) if within.notna().any() else float(insp["raw_pct"].var(ddof=1))
    sigma2 = (within.fillna(pooled) / n_surveys).rename("sigma2")

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    pooled_sd = float(np.sqrt(pooled)) if pooled == pooled else 0.0
    ci_low = []
    ci_high = []
    for ccn, part in grouped:
        lo, hi = _bootstrap_ci(part["raw_pct"].to_numpy(), rng, BOOTSTRAP_REPS, pooled_sd)
        ci_low.append((ccn, lo))
        ci_high.append((ccn, hi))
    ci_low_s = pd.Series(dict(ci_low), dtype="float64")
    ci_high_s = pd.Series(dict(ci_high), dtype="float64")
    score = empirical_bayes(raw, sigma2)
    dip = weekend_dip(daily)

    rbs = facilities.set_index("ccn")["rbs_proxy_eligible"]
    out = pd.DataFrame(
        {
            "ccn": raw.index.astype("string").str.zfill(6),
            "n_surveys": n_surveys.reindex(raw.index).astype("int64").to_numpy(),
            "raw_pct": raw.to_numpy(),
            "score_pct": score.reindex(raw.index).to_numpy(),
            "ci_low": ci_low_s.reindex(raw.index).to_numpy(),
            "ci_high": ci_high_s.reindex(raw.index).to_numpy(),
            "surge_pct": surge.reindex(raw.index).to_numpy(),
            "weekend_dip_pct": dip.reindex(raw.index).to_numpy(),
        }
    )
    # Cutoffs due 13:00 Sat — do not invent High/Watch/Low.
    out["label"] = LABEL_PLACEHOLDER
    out["trophy_flag"] = (
        rbs.reindex(out["ccn"]).fillna(False).to_numpy() & (out["ci_low"] > 0)
    )
    width = (out["ci_high"] - out["ci_low"]).median()
    print(f"median CI width: {width:.3f} percentage points")
    print(f"trophy_flag true: {int(out['trophy_flag'].sum())}")
    return out[SCORES_COLS]


def placebo_surveys(daily: pd.DataFrame, surveys: pd.DataFrame, seed: int = BOOTSTRAP_SEED) -> pd.DataFrame:
    """Assign random fake survey dates inside each facility's PBJ span."""
    rng = np.random.default_rng(seed)
    staff_dates = (
        daily.assign(date=pd.to_datetime(daily["date"]))
        .groupby("ccn")["date"]
        .agg(["min", "max"])
    )
    real = surveys.copy()
    real["survey_date"] = pd.to_datetime(real["survey_date"])
    rows = []
    for ccn, grp in real.groupby("ccn"):
        if ccn not in staff_dates.index:
            continue
        lo = staff_dates.loc[ccn, "min"] + pd.Timedelta(days=42)
        hi = staff_dates.loc[ccn, "max"] - pd.Timedelta(days=56)
        if hi < lo:
            continue
        span = pd.date_range(lo, hi, freq="D")
        n = min(len(grp), len(span))
        if n == 0:
            continue
        chosen = rng.choice(span.to_numpy(), size=n, replace=False)
        for d in chosen:
            rows.append(
                {
                    "ccn": ccn,
                    "survey_date": pd.Timestamp(d).strftime("%Y-%m-%d"),
                    "survey_type": "health_standard",
                    "source": "current",
                }
            )
    fake = pd.DataFrame(rows)
    print(f"placebo fake surveys: {len(fake)}")
    return fake


def plot_curve(curve: pd.DataFrame, path, title: str, vline_label: str) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(curve["rel_day"], curve["hprd_resid_mean"], color="#1f4e79", lw=2)
    ax.axvline(0, color="#b00020", ls="--", lw=1.2, label=vline_label)
    ax.axvspan(*PRE_RAMP, color="#f4c430", alpha=0.25, label="pre-ramp −14..−1")
    ax.axvspan(*SURGE, color="#87ceeb", alpha=0.3, label="surge 0..+3")
    ax.set_xlabel("rel_day (days relative to inspection END / CMS Survey Date)")
    ax.set_ylabel("mean hprd_resid")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"wrote {path}")
    if curve["hprd_resid_mean"].notna().any():
        peak = int(curve.loc[curve["hprd_resid_mean"].idxmax(), "rel_day"])
        print(f"  peak rel_day={peak}  max={float(curve['hprd_resid_mean'].max()):.4f}")
