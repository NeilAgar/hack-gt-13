"""`python -m pipeline` / `make data` entrypoint."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pipeline.cms import PROCESSED, ensure_raw
from pipeline.tables import build_daily_staffing, build_facilities, build_state_curve, build_surveys


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"wrote {path} rows={len(df)} cols={list(df.columns)}")


def plot_state_curve(curve: pd.DataFrame, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(curve["rel_day"], curve["hprd_resid_mean"], color="#1f4e79", lw=2)
    ax.axvline(0, color="#b00020", ls="--", lw=1.2, label="survey date (CMS)")
    ax.axvspan(-14, -1, color="#f4c430", alpha=0.25, label="pre-ramp −14..−1")
    ax.axvspan(0, 3, color="#87ceeb", alpha=0.3, label="surge 0..+3")
    ax.set_xlabel("rel_day (days relative to CMS Survey Date)")
    ax.set_ylabel("mean hprd_resid")
    ax.set_title("Georgia state-average staffing residual around surveys")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"wrote {path}")

    usable = curve.dropna(subset=["hprd_resid_mean"])
    if usable.empty:
        return {"peak_rel_day": None, "decision": "insufficient data"}
    peak = int(usable.loc[usable["hprd_resid_mean"].idxmax(), "rel_day"])
    # Architecture: if spikes peak on −4..0, treat Survey Date as exit date.
    if -4 <= peak <= 0:
        decision = "exit"
    else:
        decision = "start"
    print(f"peak rel_day={peak} -> treat survey date as {decision} date")
    return {"peak_rel_day": peak, "decision": decision, "n_rel_days": int(usable["rel_day"].nunique())}


def main(latest_quarter_only: bool = False) -> dict:
    paths = ensure_raw(latest_quarter_only=latest_quarter_only)
    facilities = build_facilities(paths["providers"], paths["citations"])
    surveys = build_surveys(paths["surveys"], facilities["ccn"])
    daily = build_daily_staffing(paths["pbj"])
    curve = build_state_curve(daily, surveys)

    write_parquet(facilities, PROCESSED / "facilities.parquet")
    write_parquet(daily, PROCESSED / "daily_staffing.parquet")
    write_parquet(surveys, PROCESSED / "surveys.parquet")
    write_parquet(curve, PROCESSED / "curves.parquet")

    print(f"GA facilities: {len(facilities)}")
    print(f"GA Health Standard surveys: {len(surveys)}")
    print(f"GA daily staffing rows: {len(daily)}")
    print(f"unique PBJ CCNs: {daily['ccn'].nunique()}")
    decision = plot_state_curve(curve, PROCESSED / "ga_state_curve.png")
    return {
        "n_facilities": int(len(facilities)),
        "n_surveys": int(len(surveys)),
        "n_daily": int(len(daily)),
        **decision,
    }


if __name__ == "__main__":
    main()
