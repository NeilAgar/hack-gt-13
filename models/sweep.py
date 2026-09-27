"""Overnight LP / capacity sweep. Writes data/processed/sweep.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from models.config import DEFAULT_MONTH, FORCED_WEEKS, PROCESSED_DIR
from models.hazard import hazard_table
from models.load import load_inputs
from models.scheduler import build_schedule, default_capacity, risk_weights
from models.simulate import simulate


def capacity_grid(n: int, n_forced: int) -> list[int]:
    """K at and above the legal forced count, around n/12.9."""
    mid = max(default_capacity(n), n_forced, 1)
    raw = {mid + d for d in (0, 1, 2, 3, 4, 6, 8)}
    return sorted(k for k in raw if k >= 1)


def sweep(
    processed_dir: Path | None = None,
    month: str = DEFAULT_MONTH,
    seed: int = 0,
    with_sim: bool = False,
) -> dict:
    processed_dir = processed_dir or PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)
    data = load_inputs(processed_dir)
    fac, surveys, scores = data["facilities"], data["surveys"], data["scores"]
    table, h, lags = hazard_table(surveys, fac)
    n = len(fac)
    n_forced = int((lags["weeks_since_last"] >= FORCED_WEEKS).sum())
    risk = risk_weights(fac, scores, lags)  # same risk (incl. time since last inspection) the schedule uses
    rows = []
    for k in capacity_grid(n, n_forced):
        plan = build_schedule(fac, scores, lags, month=month, capacity=k, seed=seed)
        probs = {r["ccn"]: r["prob"] for r in plan["probs"]}
        covered = float(sum(float(risk.get(c, 0.0)) * p for c, p in probs.items()))
        total_risk = float(risk.sum()) if len(risk) else 1.0
        row = {
            "capacity": plan["capacity"],
            "solver": plan.get("solver"),
            "n_selected": len(plan["selected"]),
            "n_forced": sum(1 for r in plan["selected"] if r["forced"]),
            "off_hours_share": (
                sum(1 for r in plan["selected"] if r["off_hours"]) / max(len(plan["selected"]), 1)
            ),
            "mean_prob": round(float(np.mean([r["prob"] for r in plan["probs"]])), 6),
            "risk_coverage": round(covered / max(total_risk, 1e-9), 6),
        }
        if with_sim:
            sim = simulate(fac, scores, surveys, h, month=month, capacity=k, seed=seed)
            row["reduction_pct"] = sim["reduction_pct"]
            row["status_quo"] = sim["status_quo"]["undetected_shirk_resident_months"]
            row["popquiz"] = sim["popquiz"]["undetected_shirk_resident_months"]
        rows.append(row)

    out = {
        "source": data.get("source"),
        "n_facilities": n,
        "n_surveys": int(len(surveys)),
        "n_forced_legal": n_forced,
        "default_capacity": default_capacity(n),
        "capacity_rule": "K = round(n_facilities / 12.9) until A supplies monthly standard-survey counts",
        "month": month,
        "hazard_rows": int(len(table)),
        "rows": rows,
    }
    (processed_dir / "sweep.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Capacity / LP sweep for StaffTrace scheduler")
    p.add_argument("--month", default=DEFAULT_MONTH)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=PROCESSED_DIR)
    p.add_argument("--sim", action="store_true", help="also run 36-month sim at each K (slow)")
    args = p.parse_args()
    sweep(processed_dir=args.out, month=args.month, seed=args.seed, with_sim=args.sim)


if __name__ == "__main__":
    main()
