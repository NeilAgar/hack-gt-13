"""CLI: python -m models  ->  data/processed/hazard.parquet + schedule/sim JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from models.config import DEFAULT_MONTH, PROCESSED_DIR
from models.hazard import bunching_share, hazard_table
from models.load import load_inputs
from models.scheduler import build_schedule, default_capacity
from models.simulate import simulate


def run(
    processed_dir: Path | None = None,
    month: str = DEFAULT_MONTH,
    capacity: int | None = None,
    seed: int = 0,
) -> dict:
    processed_dir = processed_dir or PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)
    data = load_inputs(processed_dir)
    fac, surveys, scores = data["facilities"], data["surveys"], data["scores"]

    table, h, lags = hazard_table(surveys, fac)
    table.to_parquet(processed_dir / "hazard.parquet", index=False)

    k = capacity if capacity is not None else default_capacity(len(fac))
    plan = build_schedule(fac, scores, lags, month=month, capacity=k, seed=seed)
    (processed_dir / "schedule.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    sim = simulate(fac, scores, surveys, h, month=month, capacity=k, seed=seed)
    (processed_dir / "simulate.json").write_text(json.dumps(sim, indent=2), encoding="utf-8")

    lag_map = dict(zip(lags["ccn"], lags["weeks_since_last"]))
    names = dict(zip(fac["ccn"].astype(str).str.zfill(6), fac["name"]))
    pred = []
    cur = table.merge(
        lags[["ccn", "weeks_since_last"]],
        on=["ccn", "weeks_since_last"],
        how="inner",
    )
    for rec in cur.itertuples(index=False):
        pred.append(
            {
                "ccn": rec.ccn,
                "name": names.get(rec.ccn, rec.ccn),
                "p_next_60d": round(float(rec.p_next_60d), 6),
            }
        )
    pred.sort(key=lambda r: (-r["p_next_60d"], r["ccn"]))
    (processed_dir / "predictability.json").write_text(json.dumps(pred, indent=2), encoding="utf-8")

    bunch = bunching_share(surveys)
    summary = {
        "source": data.get("source"),
        "n_facilities": int(len(fac)),
        "n_surveys": int(len(surveys)),
        "bunching_40_60": round(bunch, 4),
        "hazard_rows": int(len(table)),
        "month": month,
        "capacity": plan["capacity"],
        "solver": plan.get("solver"),
        "n_selected": len(plan["selected"]),
        "n_forced": sum(1 for r in plan["selected"] if r["forced"]),
        "off_hours_share": (
            sum(1 for r in plan["selected"] if r["off_hours"]) / max(len(plan["selected"]), 1)
        ),
        "sim_reduction_pct": sim["reduction_pct"],
        "outputs": [
            str(processed_dir / "hazard.parquet"),
            str(processed_dir / "schedule.json"),
            str(processed_dir / "simulate.json"),
            str(processed_dir / "predictability.json"),
        ],
    }
    print(json.dumps(summary, indent=2))
    _ = lag_map
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Pop Quiz models (hazard, schedule, simulate)")
    p.add_argument("--month", default=DEFAULT_MONTH, help="YYYY-MM schedule month")
    p.add_argument("--capacity", type=int, default=None, help="inspector slots this month")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=PROCESSED_DIR)
    args = p.parse_args()
    run(processed_dir=args.out, month=args.month, capacity=args.capacity, seed=args.seed)


if __name__ == "__main__":
    main()
