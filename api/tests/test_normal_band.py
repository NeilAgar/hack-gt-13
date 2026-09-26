import numpy as np
import pandas as pd
import pytest

from api import data, normal_band

DATES = pd.date_range("2024-01-01", periods=600).strftime("%Y-%m-%d").to_numpy()


def _values(seed=0):
    return np.random.default_rng(seed).normal(0, 1, len(DATES))


def test_p95_of_one_ordinary_day_matches_the_normal_distribution():
    p95, n = normal_band.normal_p95(DATES, _values(), [], 1, "115001")
    assert n == 600 and 1.4 < p95 < 1.9  # true 95th percentile of N(0,1) is 1.645


def test_days_near_an_inspection_are_excluded():
    v = _values()
    v[290:311] = 50.0  # a huge spike around the "inspection" on day 300
    with_spike, n = normal_band.normal_p95(DATES, v, [DATES[300]], 1, "115001")
    base, _ = normal_band.normal_p95(DATES, _values(), [DATES[300]], 1, "115001")
    assert with_spike == base and n == 600 - 121  # +-60 days removed


def test_averaging_more_inspections_lowers_the_line():
    one, _ = normal_band.normal_p95(DATES, _values(), [], 1, "115001")
    two, _ = normal_band.normal_p95(DATES, _values(), [], 2, "115001")
    assert two < one


def test_deterministic_and_null_when_too_few_days():
    a = normal_band.normal_p95(DATES, _values(), [], 2, "11A186")
    assert a == normal_band.normal_p95(DATES, _values(), [], 2, "11A186")
    assert normal_band.normal_p95(DATES[:50], _values()[:50], [], 1, "115001")[0] is None


def test_real_data_line_is_calibrated():
    """Far from inspections, a home's curve should sit above its own 95th-percentile line ~5% of the time."""
    if not (data.ROOT / "data" / "processed" / "daily_staffing.parquet").exists():
        pytest.skip("no processed data")
    curves = pd.read_parquet(data.ROOT / "data" / "processed" / "curves.parquet")
    homes = curves[curves["ccn"] != "GA"]
    lines = {c: p for c, (p, _) in normal_band.all_homes(data.ROOT / "data" / "processed", homes).items() if p is not None}
    far = homes[(homes["rel_day"].abs() >= 15) & homes["ccn"].isin(lines)]
    share = (far["hprd_resid_mean"] > far["ccn"].map(lines)).mean()
    assert 0.02 < share < 0.10
