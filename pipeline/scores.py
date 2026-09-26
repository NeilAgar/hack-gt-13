"""Survey-responsiveness scores (Chen & Dillender w34037, mapped onto CONTRACTS.md).

Day 0 is the inspection END date (CMS Survey Date). Paper §3.1 / eq. (1):
inspectors must report end dates; start dates are unreliable, so they do not
shift the event study to start. Peak staffing is on day −1; hours collapse on +1.

Scored window −14..−1 is the 14 days through the last inspection day (it
includes the inspection). Do not describe it as "before inspections".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.cms import (
    BASELINE,
    BOOTSTRAP_REPS,
    BOOTSTRAP_SEED,
    HEADLINE_TEMPLATE,
    OVERLAP_DAYS,
    PRE_RAMP,
    PROCESSED,
    SCORES_COLS,
    SURGE,
    WATCH_CI_HIGH_MIN,
)
from pipeline.tables import drop_overlapping_surveys, event_panel


def format_headline(score_pct: float, ci_low: float, ci_high: float, n_surveys: int) -> str:
    direction = "higher" if score_pct >= 0 else "lower"
    return HEADLINE_TEMPLATE.format(
        abs_pct=abs(float(score_pct)),
        direction=direction,
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        n=int(n_surveys),
    )


def assign_label(score_pct: float, ci_low: float, ci_high: float) -> str:
    """Staffing Consistency. Low = CI entirely above 0 (survey-responsive staffing)."""
    if ci_low > 0:
        return "Low"
    if ci_high > WATCH_CI_HIGH_MIN:
        return "Watch"
    return "High"


def _window_mean(panel: pd.DataFrame, lo: int, hi: int, value_col: str) -> pd.Series:
    sub = panel.loc[panel["rel_day"].between(lo, hi) & panel[value_col].notna()]
    return sub.groupby(["ccn", "survey_date"])[value_col].mean()


def inspection_contrasts(daily: pd.DataFrame, surveys: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    usable = out["pre_n"].fillna(0).ge(7) & out["base_n"].fillna(0).ge(14) & out["base_hprd"].gt(0)
    out = out.loc[usable].copy()
    out["raw_pct"] = (out["pre_hprd"] - out["base_hprd"]) / out["base_hprd"] * 100.0
    out["surge_pct"] = (out["surge_hprd"] - out["base_hprd"]) / out["base_hprd"] * 100.0
    # One bad census day can produce 400% contrasts; cap before means/CIs/EB.
    lo, hi = out["raw_pct"].quantile(0.025), out["raw_pct"].quantile(0.975)
    out["raw_pct"] = out["raw_pct"].clip(lo, hi)
    print(f"usable inspections for scores: {len(out)} (winsorize raw_pct to [{lo:.1f}, {hi:.1f}])")
    return out, panel


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


def _day_bootstrap_pct(pre: np.ndarray, base: np.ndarray, rng: np.random.Generator, reps: int) -> np.ndarray:
    pre = np.asarray(pre, dtype=float)
    base = np.asarray(base, dtype=float)
    pre = pre[np.isfinite(pre)]
    base = base[np.isfinite(base)]
    if len(pre) < 3 or len(base) < 3:
        return np.array([])
    p = rng.choice(pre, size=(reps, len(pre)), replace=True).mean(axis=1)
    b = rng.choice(base, size=(reps, len(base)), replace=True).mean(axis=1)
    ok = b > 0.05
    pct = np.full(reps, np.nan)
    pct[ok] = (p[ok] - b[ok]) / b[ok] * 100.0
    return pct[np.isfinite(pct)]


def _facility_ci(
    ccn: str,
    part: pd.DataFrame,
    panel: pd.DataFrame,
    rng: np.random.Generator,
    clip: tuple[float, float],
) -> tuple[float, float]:
    values = part["raw_pct"].to_numpy()
    if len(values) >= 2:
        draws = rng.choice(values, size=(BOOTSTRAP_REPS, len(values)), replace=True).mean(axis=1)
        return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))
    # One inspection: bootstrap days in the scored windows, not the cross-home SD.
    one = part.iloc[0]
    days = panel.loc[
        (panel["ccn"] == ccn)
        & (pd.to_datetime(panel["survey_date"]) == pd.to_datetime(one["survey_date"]))
    ]
    pre = days.loc[days["rel_day"].between(*PRE_RAMP), "hprd"].to_numpy()
    base = days.loc[days["rel_day"].between(*BASELINE), "hprd"].to_numpy()
    draws = _day_bootstrap_pct(pre, base, rng, BOOTSTRAP_REPS)
    if len(draws) < 20:
        v = float(values[0])
        return (v, v)
    draws = np.clip(draws, clip[0], clip[1])
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def empirical_bayes(raw: pd.Series, sigma2: pd.Series) -> tuple[pd.Series, pd.Series, float]:
    state_mean = float(raw.mean())
    tau2 = float(max(0.0, raw.var(ddof=1) - sigma2.mean()))
    w = tau2 / (tau2 + sigma2)
    w = w.fillna(0.0)
    print(f"EB tau2={tau2:.4f} state_mean_raw={state_mean:.3f}%")
    score = w * raw + (1.0 - w) * state_mean
    return score, w, state_mean


def build_scores(daily: pd.DataFrame, surveys: pd.DataFrame, facilities: pd.DataFrame) -> pd.DataFrame:
    insp, panel = inspection_contrasts(daily, surveys)
    clip = (float(insp["raw_pct"].min()), float(insp["raw_pct"].max()))
    counts = insp.groupby("ccn").size()
    print(
        f"homes with usable inspections: 1={int((counts == 1).sum())}  "
        f"2={int((counts == 2).sum())}  3+={int((counts >= 3).sum())}"
    )

    grouped = insp.groupby("ccn")
    raw = grouped["raw_pct"].mean()
    surge = grouped["surge_pct"].mean()
    n_surveys = grouped.size().astype("int64")
    within = grouped["raw_pct"].var(ddof=1)
    pooled = float(within.dropna().mean()) if within.notna().any() else float(insp["raw_pct"].var(ddof=1))
    sigma2 = (within.fillna(pooled) / n_surveys).rename("sigma2")

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    ci_low_s = {}
    ci_high_s = {}
    for ccn, part in grouped:
        lo, hi = _facility_ci(ccn, part, panel, rng, clip)
        ci_low_s[ccn] = lo
        ci_high_s[ccn] = hi
    score, w, state_mean = empirical_bayes(raw, sigma2)
    dip = weekend_dip(daily)

    ci_low = pd.Series(ci_low_s).reindex(raw.index)
    ci_high = pd.Series(ci_high_s).reindex(raw.index)
    w = w.reindex(raw.index)
    score = score.reindex(raw.index)
    # Posterior SD scales by sqrt(w): keep the raw interval's shape around the shrunk score.
    k = np.sqrt(w)
    ci_low = score - k * (raw - ci_low)
    ci_high = score + k * (ci_high - raw)

    rbs = facilities.set_index("ccn")["rbs_proxy_eligible"]
    names = facilities.set_index("ccn")["name"]
    out = pd.DataFrame(
        {
            "ccn": raw.index.astype("string").str.zfill(6),
            "n_surveys": n_surveys.reindex(raw.index).astype("int64").to_numpy(),
            "raw_pct": raw.to_numpy(),
            "score_pct": score.reindex(raw.index).to_numpy(),
            "ci_low": ci_low.to_numpy(),
            "ci_high": ci_high.to_numpy(),
            "surge_pct": surge.reindex(raw.index).to_numpy(),
            "weekend_dip_pct": dip.reindex(raw.index).to_numpy(),
        }
    )
    out["label"] = [
        assign_label(s, lo, hi)
        for s, lo, hi in zip(out["score_pct"], out["ci_low"], out["ci_high"])
    ]
    out["trophy_flag"] = (
        rbs.reindex(out["ccn"]).fillna(False).to_numpy() & (out["ci_low"] > 0)
    )
    width = (out["ci_high"] - out["ci_low"]).median()
    print(f"median CI width: {width:.3f} percentage points")
    print(out["label"].value_counts().to_string())
    trophies = out.loc[out["trophy_flag"]].copy()
    trophies["name"] = trophies["ccn"].map(names)
    print(f"trophy_flag true: {len(trophies)}")
    if len(trophies):
        print(
            trophies.sort_values("score_pct", ascending=False)[
                ["ccn", "name", "n_surveys", "score_pct", "ci_low", "ci_high", "label"]
            ].to_string(index=False)
        )
    example = out.iloc[0]
    print("headline example:")
    print(
        "  "
        + format_headline(
            example["score_pct"], example["ci_low"], example["ci_high"], int(example["n_surveys"])
        )
    )
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
    ax.axvspan(*PRE_RAMP, color="#f4c430", alpha=0.25, label="through last inspection day −14..−1")
    ax.axvspan(*SURGE, color="#87ceeb", alpha=0.3, label="post-exit 0..+3")
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
