import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import data, evidence
from api.main import app

client = TestClient(app)


def _curve(ccn, spike):
    return pd.DataFrame([{"ccn": ccn, "rel_day": d, "hprd_resid_mean": (spike if -4 <= d <= -1 else 0.0), "n_obs": 500}
                         for d in range(-42, 57)])


@pytest.fixture
def processed(tmp_path, monkeypatch):
    d = tmp_path / "processed"
    d.mkdir()
    _curve("GA", 0.2).to_parquet(d / "curves.parquet")
    _curve("GA", 0.0).to_parquet(d / "placebo_curve.parquet")
    pd.DataFrame({"ccn": ["115001"] * 4, "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
                  "hprd": [4.0, 4.0, 4.0, 4.0]}).to_parquet(d / "daily_staffing.parquet")
    pd.DataFrame({"ccn": ["115001", "115001"], "survey_date": ["2024-01-02", "2019-05-01"],
                  "survey_type": ["health_standard"] * 2, "source": ["current"] * 2}).to_parquet(d / "surveys.parquet")
    pd.DataFrame({"ccn": ["115001"], "label": ["Low"], "trophy_flag": [True],
                  "weekend_dip_pct": [12.0]}).to_parquet(d / "scores.parquet")
    monkeypatch.setattr(data, "PROCESSED", d)
    evidence.evidence.cache_clear()
    yield
    evidence.evidence.cache_clear()


def test_evidence_numbers_come_from_the_tables(processed):
    ev = client.get("/api/evidence").json()
    assert ev["real"]["on_site"] == 0.2 and ev["real"]["on_site_pct"] == 5.0  # 0.2 / 4.0 mean HPRD
    assert ev["real"]["pre_arrival"] == 0.0 and ev["real"]["peak_day"] in range(-4, 0)
    assert ev["placebo"]["on_site"] == 0.0
    assert ev["sample"]["inspections"] == 1  # the 2019 survey is outside the staffing window
    assert ev["scores"] == {"scored": 1, "labels": {"Low": 1}, "trophy": 1, "median_weekend_dip_pct": 12.0}
    assert len(ev["state_curve"]) == len(ev["placebo_curve"]) == 99


def test_evidence_without_tables_is_503(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "PROCESSED", tmp_path / "none")
    evidence.evidence.cache_clear()
    assert client.get("/api/evidence").status_code == 503
    evidence.evidence.cache_clear()


def test_evidence_page_is_served_with_required_notes():
    r = client.get("/evidence")
    assert r.status_code == 200 and "/api/evidence" in r.text
    for must in ("self-reported", "w34037", "w34491", "Placebo"):
        assert must in r.text
    assert "gaming" not in r.text.lower()
