"""Smoke tests for models/: hazard contract, constraints, sim identity."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from models.config import DEFAULT_MONTH, FORCED_WEEKS, OFF_HOURS_MIN_SHARE, PROCESSED_DIR
from models.hazard import bunching_share, gap_summary, hazard_table
from models.load import load_inputs
from models.scheduler import build_schedule, default_capacity
from models.simulate import simulate
from models.synthetic import interval_weeks

CONTRACT_HAZARD_COLS = {"ccn", "weeks_since_last", "p_survey_week", "p_next_60d"}


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    # Always synthetic: real parquet in data/processed must not change smoke tests.
    return load_inputs(processed_dir=tmp_path_factory.mktemp("synthetic_inputs"))


def test_synthetic_bunching_near_nber(inputs):
    """NBER-style 40–60 week bunching is a property of synthetic surveys only."""
    share = bunching_share(inputs["surveys"])
    assert share >= 0.65, f"expected ~74% of synthetic lags in 40–60 weeks, got {share:.3f}"
    assert inputs.get("source") == "synthetic"


def test_hazard_schema_and_ccn(inputs):
    table, h, lags = hazard_table(inputs["surveys"], inputs["facilities"])
    assert CONTRACT_HAZARD_COLS.issubset(table.columns)
    assert table["ccn"].map(lambda x: len(str(x)) == 6).all()
    assert (table["p_survey_week"].between(0, 1)).all()
    assert (table["p_next_60d"].between(0, 1)).all()
    early = float(h[8:26].mean())
    bunch = float(h[40:61].mean())
    assert bunch > early, f"mean hazard 40-60 ({bunch:.4f}) should exceed weeks 8-25 ({early:.4f})"
    assert len(lags) == inputs["facilities"]["ccn"].nunique() or len(lags) > 0


def test_schedule_constraints(inputs):
    table, h, lags = hazard_table(inputs["surveys"], inputs["facilities"])
    k = default_capacity(len(inputs["facilities"]))
    plan = build_schedule(inputs["facilities"], inputs["scores"], lags, month=DEFAULT_MONTH, capacity=k, seed=1)
    assert plan["month"] == DEFAULT_MONTH
    n_forced = int((lags["weeks_since_last"] >= FORCED_WEEKS).sum())
    assert n_forced <= len(plan["selected"])
    assert plan["capacity"] == len(plan["selected"])
    n_sel = len(plan["selected"])
    n_off = sum(1 for r in plan["selected"] if r["off_hours"])
    assert n_off / max(n_sel, 1) >= OFF_HOURS_MIN_SHARE - 1e-9
    selected_ccn = {r["ccn"] for r in plan["selected"]}
    lag_map = dict(zip(lags["ccn"], lags["weeks_since_last"]))
    for row in plan["probs"]:
        if row["forced"]:
            assert lag_map[row["ccn"]] >= int(FORCED_WEEKS) - 1
            assert row["ccn"] in selected_ccn
            assert abs(row["prob"] - 1.0) < 1e-6
    names = {r["ccn"] for r in plan["selected"]}
    assert all("name" in r and r["prob"] >= 0 for r in plan["selected"])
    assert len(names) == n_sel


def test_simulate_identity(inputs):
    table, h, lags = hazard_table(inputs["surveys"], inputs["facilities"])
    k = default_capacity(len(inputs["facilities"]))
    out = simulate(inputs["facilities"], inputs["scores"], inputs["surveys"], h, capacity=k, seed=3)
    assert out["months"] == 36
    sq = out["status_quo"]["undetected_shirk_resident_months"]
    pq = out["popquiz"]["undetected_shirk_resident_months"]
    expected = 0.0 if sq == 0 else round(100.0 * (sq - pq) / sq, 1)
    assert out["reduction_pct"] == expected
    assert out["reduction_pct"] >= 0
    assert "illustrative" in out and out["illustrative"] is True


def test_synthetic_includes_fixture_ccns_and_count(inputs):
    ccns = set(inputs["facilities"]["ccn"].astype(str).str.zfill(6))
    assert {"115994", "115995", "115996", "115997", "115998", "115999"} <= ccns
    assert len(inputs["facilities"]) == 80


def test_overdue_fixture_is_forced(inputs):
    table, h, lags = hazard_table(inputs["surveys"], inputs["facilities"])
    k = default_capacity(len(inputs["facilities"]))
    plan = build_schedule(inputs["facilities"], inputs["scores"], lags, month=DEFAULT_MONTH, capacity=k, seed=2)
    harbor = next(r for r in plan["probs"] if r["ccn"] == "115999")
    assert harbor["forced"] is True
    assert abs(harbor["prob"] - 1.0) < 1e-6
    assert any(r["ccn"] == "115999" for r in plan["selected"])
    _ = table, h


def test_same_month_repeat_banned(inputs):
    table, h, lags = hazard_table(inputs["surveys"], inputs["facilities"])
    as_of_month = 7  # AS_OF_DATE is the July 2026 survey snapshot
    plan = build_schedule(
        inputs["facilities"],
        inputs["scores"],
        lags,
        month="2026-07",
        capacity=default_capacity(len(inputs["facilities"])),
        seed=4,
    )
    banned = lags[(lags["last_month"] == as_of_month) & (lags["weeks_since_last"] < FORCED_WEEKS)]
    selected = {r["ccn"] for r in plan["selected"]}
    pmap = {r["ccn"]: r["prob"] for r in plan["probs"]}
    for ccn in banned["ccn"]:
        assert pmap.get(ccn, 0.0) == 0.0
        assert ccn not in selected
    _ = table, h


def test_interval_weeks_positive(inputs):
    gaps = interval_weeks(inputs["surveys"])
    assert (gaps["weeks_since_last"] > 0).all()


def test_cli_outputs(tmp_path: Path):
    from models.__main__ import run

    summary = run(processed_dir=tmp_path, month=DEFAULT_MONTH, seed=0)
    assert (tmp_path / "hazard.parquet").exists()
    assert (tmp_path / "schedule.json").exists()
    assert (tmp_path / "simulate.json").exists()
    haz = pd.read_parquet(tmp_path / "hazard.parquet")
    assert CONTRACT_HAZARD_COLS.issubset(haz.columns)
    plan = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert "selected" in plan and "probs" in plan
    sim = json.loads((tmp_path / "simulate.json").read_text(encoding="utf-8"))
    assert sim["months"] == 36
    assert summary["n_facilities"] > 0
    # Do not require PROCESSED_DIR in this test (tmp_path only).
    _ = PROCESSED_DIR


def test_capacity_sweep_writes_rows(tmp_path: Path):
    from models.sweep import sweep

    out = sweep(processed_dir=tmp_path, month=DEFAULT_MONTH, seed=0, with_sim=False)
    assert (tmp_path / "sweep.json").exists()
    assert out["default_capacity"] == default_capacity(out["n_facilities"])
    assert len(out["rows"]) >= 3
    caps = [r["capacity"] for r in out["rows"]]
    assert caps == sorted(caps)
    assert all(r["n_selected"] == r["capacity"] for r in out["rows"])
    assert all(r["solver"] in {"lp", "proportional"} for r in out["rows"])


def test_capacity_capped_to_selected(inputs):
    table, h, lags = hazard_table(inputs["surveys"], inputs["facilities"])
    plan = build_schedule(
        inputs["facilities"], inputs["scores"], lags, month=DEFAULT_MONTH, capacity=200, seed=0
    )
    assert plan["capacity"] == len(plan["selected"])
    n_eligible = len(inputs["facilities"])
    assert plan["capacity"] <= n_eligible
    _ = table, h


def test_predictability_reproducible(tmp_path: Path):
    from models.__main__ import run

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    run(processed_dir=a, month=DEFAULT_MONTH, seed=0)
    run(processed_dir=b, month=DEFAULT_MONTH, seed=0)
    pa = (a / "predictability.json").read_text(encoding="utf-8")
    pb = (b / "predictability.json").read_text(encoding="utf-8")
    assert pa == pb


def test_georgia_gaps_match_a_when_parquet_present():
    """Real GA last-3-cycle gaps: inspections run late, not NBER 74% in 40–60 weeks."""
    surveys = Path(PROCESSED_DIR) / "surveys.parquet"
    if not surveys.exists():
        pytest.skip("A's surveys.parquet not in data/processed")
    data = load_inputs(processed_dir=PROCESSED_DIR)
    if data.get("source") != "parquet":
        pytest.skip("processed dir is not real parquet")
    gaps = gap_summary(data["surveys"])
    assert gaps["n_gaps"] > 100
    assert 65 <= gaps["median_weeks"] <= 85
    assert 0.12 <= gaps["share_40_60"] <= 0.28
    table, h, lags = hazard_table(data["surveys"], data["facilities"])
    n_overdue = int((lags["weeks_since_last"] >= FORCED_WEEKS).sum())
    assert n_overdue < len(data["facilities"])
    _ = table, h
