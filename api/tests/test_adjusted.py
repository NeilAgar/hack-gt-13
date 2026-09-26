import pytest

from api import adjusted

AVG = 1.2
BASE = {"overall_star": 5, "score_pct": 3.7, "ci_low": 2.3, "ci_high": 5.1, "n_surveys": 2}


def test_downgrades_one_star_when_clearly_above_state_average_with_two_inspections():
    star, reason = adjusted.adjust(BASE, AVG)
    assert star == 4
    assert "5★, adjusted to 4★" in reason and "3.7%" in reason and "2 inspections" in reason and "1.2%" in reason


@pytest.mark.parametrize("change, why", [
    ({"ci_low": 1.2}, "not clearly above the Georgia average"),   # range touches the average
    ({"ci_low": 0.5}, "not clearly above the Georgia average"),   # above zero isn't enough
    ({"n_surveys": 1}, "only 1 inspection"),
    ({"score_pct": None, "ci_low": None, "ci_high": None, "n_surveys": None}, "not enough inspections"),
])
def test_keeps_cms_rating_without_clear_repeated_evidence(change, why):
    star, reason = adjusted.adjust(BASE | change, AVG)
    assert star == 5 and reason.startswith("Same as the CMS overall rating (5★)") and why in reason


def test_never_below_one_star_and_never_invents_a_rating():
    star, reason = adjusted.adjust(BASE | {"overall_star": 1}, AVG)
    assert star == 1 and "already the lowest" in reason
    assert adjusted.adjust(BASE | {"overall_star": None}, AVG)[0] is None


def test_never_raises_a_rating():
    for lo in (-10.0, 0.0, 1.0, 5.0):
        for star in range(1, 6):
            assert adjusted.adjust(BASE | {"overall_star": star, "ci_low": lo}, AVG)[0] <= star


def test_state_average_ignores_missing():
    assert adjusted.state_average([1.0, None, 3.0]) == 2.0


def test_adjusted_rating_on_real_data_is_consistent():
    from api import data
    p = data._processed()
    if p is None:
        pytest.skip("no processed data")
    for r in p["details"].values():
        if r["overall_star"] is None:
            assert r["adjusted_star"] is None
        else:
            assert r["adjusted_star"] in (r["overall_star"], r["overall_star"] - 1)
            assert r["adjusted_star"] >= 1 and r["adjust_reason"]
            if r["adjusted_star"] < r["overall_star"]:
                assert r["n_surveys"] >= 2 and "survey-responsive staffing" in r["adjust_reason"]


def test_low_label_and_star_drop_use_the_same_evidence():
    """Every home the star rule would lower is labeled Low, and every Low home would be lowered unless it
    has no CMS rating or is already at 1 star (those guards only stop the displayed star from changing)."""
    from api import data
    p = data._processed()
    if p is None:
        pytest.skip("no processed data")
    rows = [r for r in p["details"].values() if r.get("score_pct") is not None]
    avg = adjusted.state_average(r["raw_pct"] for r in rows)
    for r in rows:
        evidence = r["n_surveys"] >= adjusted.MIN_INSPECTIONS and r["ci_low"] > avg
        assert (r["label"] == "Low") == evidence, r["ccn"]
        if r["adjusted_star"] is not None and r["adjusted_star"] < r["overall_star"]:
            assert r["label"] == "Low", r["ccn"]
        if r["label"] == "Low" and r["overall_star"] not in (None, 1):
            assert r["adjusted_star"] == r["overall_star"] - 1, r["ccn"]
