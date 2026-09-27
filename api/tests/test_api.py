import httpx
import pytest
from fastapi.testclient import TestClient

from api import explain as explain_mod
from api.main import app

client = TestClient(app)
REG = {"X-Demo-Role": "regulator"}
TIMING_KEYS = {"p_next_60d", "p_survey_week", "weeks_since_last", "next_survey", "predictability"}


@pytest.fixture(autouse=True)
def fixture_mode(tmp_path, monkeypatch):
    """Family endpoints read fixtures/ by default, so these tests don't depend on A's current data."""
    from api import data
    monkeypatch.setattr(data, "PROCESSED", tmp_path / "empty")
    data._processed.cache_clear()
    yield
    data._processed.cache_clear()


@pytest.fixture(autouse=True)
def clear_explain_cache():
    explain_mod._cache.clear()
    yield
    explain_mod._cache.clear()


def keys(obj):
    if isinstance(obj, dict):
        return set(obj) | set().union(*(keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(keys(v) for v in obj)) if obj else set()
    return set()


def test_facilities_contract_fields():
    rows = client.get("/api/facilities").json()
    assert rows
    expected = {"ccn", "name", "city", "lat", "lon", "overall_star", "adjusted_star", "staffing_star",
                "score_pct", "ci_low", "ci_high", "label"}
    assert all(set(r) == expected for r in rows)


def test_facilities_search_and_limit():
    rows = client.get("/api/facilities", params={"q": "savannah"}).json()
    assert rows and all(r["city"] == "Savannah" for r in rows)
    assert len(client.get("/api/facilities", params={"limit": 1}).json()) == 1


def test_facility_detail():
    fac = client.get("/api/facility/115999").json()
    assert fac["curve"] and fac["state_curve"]
    assert {"score_pct", "ci_low", "ci_high", "explanation"} <= set(fac)
    assert client.get("/api/facility/000000").status_code == 404


def test_public_endpoints_never_expose_timing():
    for path in ["/api/facilities", "/api/facility/115999", "/api/facility/115998"]:
        assert not keys(client.get(path).json()) & TIMING_KEYS, path


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/schedule", {"month": "2026-10", "capacity": 3}),
    ("get", "/api/simulate?capacity=3", None),
    ("get", "/api/predictability", None),
    ("get", "/api/backlog", None),
])
def test_regulator_endpoints_need_header(method, path, body):
    kw = {"json": body} if body else {}
    assert getattr(client, method)(path, **kw).status_code == 403
    assert getattr(client, method)(path, headers={"X-Demo-Role": "family"}, **kw).status_code == 403
    assert getattr(client, method)(path, headers=REG, **kw).status_code == 200


def test_schedule_shape_and_validation():
    s = client.post("/api/schedule", json={"month": "2026-10", "capacity": 3}, headers=REG).json()
    assert {"month", "capacity", "selected", "probs"} <= set(s)
    assert client.post("/api/schedule", json={"month": "2026-13", "capacity": 3}, headers=REG).status_code == 422


def test_explain_without_key_uses_template(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    text = client.post("/api/explain", json={"ccn": "115999"}).json()["text"]
    assert "survey-responsive staffing" in text and "10.8%" in text and "4.9%" in text


def _fake_grok(reply):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


FAC = {"name": "Sample Harbor", "city": "Savannah", "n_surveys": 3, "score_pct": 10.8,
       "ci_low": 4.9, "ci_high": 16.2, "label": "Low"}


def test_explain_keeps_faithful_grok_reply(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test")
    reply = "Sample Harbor showed survey-responsive staffing of 10.8% (range 4.9% to 16.2%, 3 inspections)."
    assert explain_mod.explain(FAC, client=_fake_grok(reply)) == reply


@pytest.mark.parametrize("reply", [
    "Staffing was 12% higher before inspections.",          # invented number
    "Sample Harbor may be gaming inspections by 10.8%.",     # banned word
])
def test_explain_rejects_unfaithful_grok_reply(monkeypatch, reply):
    monkeypatch.setenv("XAI_API_KEY", "test")
    assert explain_mod.explain(FAC, client=_fake_grok(reply)) == explain_mod.template(FAC)


def test_template_verdict_follows_ci():
    assert "called survey-responsive" in explain_mod.template(FAC)
    flat = {**FAC, "score_pct": -0.8, "ci_low": -4.0, "ci_high": 2.4}
    assert "0.8% lower" in explain_mod.template(flat) and "no clear sign" in explain_mod.template(flat)


SCHEDULE_KEYS = {"month", "capacity", "selected", "probs"}
SIMULATE_KEYS = {"months", "status_quo", "popquiz", "reduction_pct"}


def test_schedule_follows_requested_capacity_and_month():
    for k in (5, 9):
        r = client.post("/api/schedule", json={"month": "2026-11", "capacity": k, "seed": 1}, headers=REG)
        s = r.json()
        assert r.headers["X-Data-Source"].startswith("models:")
        assert set(s) == SCHEDULE_KEYS
        n_forced = sum(p["forced"] for p in s["probs"])
        # Legally forced homes are always scheduled, so capacity can rise above the request.
        assert s["month"] == "2026-11" and s["capacity"] == max(k, n_forced) == len(s["selected"])
        assert abs(sum(p["prob"] for p in s["probs"]) - s["capacity"]) < 1e-3
        assert all(p["prob"] == 1.0 for p in s["probs"] if p["forced"])


def test_schedule_seed_reproduces_plan():
    body = {"month": "2026-11", "capacity": 6, "seed": 3}
    first = client.post("/api/schedule", json=body, headers=REG).json()
    assert client.post("/api/schedule", json=body, headers=REG).json() == first


def test_simulate_from_models_matches_contract():
    r = client.get("/api/simulate", params={"capacity": 6}, headers=REG)
    assert r.headers["X-Data-Source"].startswith("models:")
    assert set(r.json()) == SIMULATE_KEYS and r.json()["months"] == 36


def test_regulator_falls_back_to_fixtures_without_models(monkeypatch):
    from api import data
    monkeypatch.setattr(data, "_models", lambda: None)
    data.simulate.cache_clear()
    r = client.post("/api/schedule", json={"month": "2026-10", "capacity": 3}, headers=REG)
    assert r.headers["X-Data-Source"] == "fixtures" and r.json() == data._load("schedule_sample.json")
    assert client.get("/api/simulate?capacity=3", headers=REG).json() == data._load("simulate_sample.json")
    assert client.get("/api/backlog", headers=REG).json() == data._load("backlog_sample.json")
    data.simulate.cache_clear()


def test_trophy_check_is_gone():
    assert client.get("/api/trophy", headers=REG).status_code == 404
    assert all("trophy_flag" not in r for r in client.get("/api/facilities").json())


def test_schedule_capacity_above_eligible_pool_is_consistent():
    s = client.post("/api/schedule", json={"month": "2026-10", "capacity": 1000, "seed": 1}, headers=REG).json()
    assert s["capacity"] == len(s["selected"]) < 1000


def test_schedule_rejects_negative_seed():
    r = client.post("/api/schedule", json={"month": "2026-10", "capacity": 3, "seed": -1}, headers=REG)
    assert r.status_code == 422


def test_predictability_comes_from_models():
    from api import data
    m = data._models()
    rows = client.get("/api/predictability", headers=REG).json()
    ccns = set(m["facilities"]["ccn"].astype(str).str.zfill(6))
    # Homes with no survey on record have no hazard row, so this can be shorter than the facility list.
    assert rows and {r["ccn"] for r in rows} <= ccns and set(rows[0]) == {"ccn", "name", "p_next_60d"}
    assert rows == sorted(rows, key=lambda r: (-r["p_next_60d"], r["ccn"]))


def _counting_grok(reply, calls):
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_explain_caches_grok_reply(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test")
    reply = "Sample Harbor showed survey-responsive staffing of 10.8% (range 4.9% to 16.2%)."
    calls = []
    grok = _counting_grok(reply, calls)
    assert explain_mod.explain(FAC, client=grok) == reply
    assert explain_mod.explain(FAC, client=grok) == reply
    assert len(calls) == 1 and explain_mod.cached(FAC) == reply


def test_explain_timeout_falls_back_and_is_not_cached(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test")

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    grok = httpx.Client(transport=httpx.MockTransport(slow))
    assert explain_mod.explain(FAC, client=grok) == explain_mod.template(FAC)
    assert explain_mod.cached(FAC) is None


def test_rejected_reply_is_not_cached(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test")
    explain_mod.explain(FAC, client=_fake_grok("Staffing was 12% higher."))
    assert explain_mod.cached(FAC) is None


def test_grok_timeout_is_under_web_timeout():
    assert explain_mod.GROK_TIMEOUT_S < 4  # web/lib/api.ts API_TIMEOUT_MS default


def test_facility_includes_cached_explanation(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test")
    assert client.get("/api/facility/115999").json()["explanation"] is None
    reply = "Sample Harbor Health & Rehab showed survey-responsive staffing of 10.8% (range 4.9% to 16.2%)."
    from api import data
    explain_mod.explain(data.facility("115999"), client=_fake_grok(reply))
    assert client.get("/api/facility/115999").json()["explanation"] == reply


# --- Family endpoints on A's processed tables ---------------------------------------------

def _write_processed(d):
    import pandas as pd
    d.mkdir()
    pd.DataFrame([
        {"ccn": "115001", "name": "Alpha Care", "city": "Macon", "county": "Bibb", "lat": 32.8, "lon": -83.6,
         "certified_beds": 100, "avg_residents": 80.5, "ownership": "For profit", "overall_star": 5,
         "staffing_star": 4, "health_star": 5, "harm_citations_3y": 0, "ij_citations_3y": 0},
        {"ccn": "115002", "name": "Beta Home", "city": "Savannah", "county": "Chatham", "lat": 32.1, "lon": -81.1,
         "certified_beds": 60, "avg_residents": 50.0, "ownership": "Non profit", "overall_star": 2,
         "staffing_star": 2, "health_star": 2, "harm_citations_3y": 1, "ij_citations_3y": 0},
    ]).astype({"overall_star": "Int64"}).to_parquet(d / "facilities.parquet")
    pd.DataFrame([{"ccn": "115001", "n_surveys": 2, "raw_pct": 9.0, "score_pct": 7.5, "ci_low": 2.0,
                   "ci_high": 13.0, "surge_pct": 12.0, "weekend_dip_pct": -4.0, "label": "PLACEHOLDER"}]).to_parquet(d / "scores.parquet")
    pd.DataFrame([{"ccn": "GA", "rel_day": 0, "hprd_resid_mean": 0.3, "n_obs": 500},
                  {"ccn": "GA", "rel_day": -1, "hprd_resid_mean": 0.34, "n_obs": 500},
                  {"ccn": "115001", "rel_day": -1, "hprd_resid_mean": 0.5, "n_obs": 2}]).to_parquet(d / "curves.parquet")


@pytest.fixture
def processed(tmp_path, monkeypatch):
    from api import data
    d = tmp_path / "processed"
    _write_processed(d)
    monkeypatch.setattr(data, "PROCESSED", d)
    data._processed.cache_clear()
    return d


def test_family_serves_processed_tables(processed):
    r = client.get("/api/facilities")
    assert r.headers["X-Data-Source"] == "processed"
    rows = {f["ccn"]: f for f in r.json()}
    assert set(rows) == {"115001", "115002"}
    assert all(set(f) == {"ccn", "name", "city", "lat", "lon", "overall_star", "adjusted_star", "staffing_star",
                          "score_pct", "ci_low", "ci_high", "label"} for f in rows.values())
    assert rows["115001"]["score_pct"] == 7.5
    assert client.get("/api/facilities", params={"q": "savannah"}).json()[0]["ccn"] == "115002"


def test_facility_detail_from_processed(processed):
    fac = client.get("/api/facility/115001").json()
    assert fac["n_surveys"] == 2 and isinstance(fac["n_surveys"], int)
    assert fac["curve"] == [{"d": -1, "v": 0.5}]
    assert fac["state_curve"] == [{"d": -1, "v": 0.34}, {"d": 0, "v": 0.3}]  # sorted by day
    assert fac["label"] is None  # PLACEHOLDER isn't a contract label


def test_home_without_score_has_nulls_and_explains_why(processed):
    fac = client.get("/api/facility/115002").json()
    assert fac["score_pct"] is None and fac["ci_low"] is None and fac["curve"] == []
    assert fac["label"] is None
    assert client.post("/api/explain", json={"ccn": "115002"}).json()["text"] == explain_mod.NO_SCORE


def test_real_processed_data_smoke(monkeypatch):
    """Runs on A's committed tables, if present: every home serializes and the curves are there."""
    from api import data
    if not (data.ROOT / "data" / "processed" / "scores.parquet").exists():
        pytest.skip("no processed data")
    monkeypatch.setattr(data, "PROCESSED", data.ROOT / "data" / "processed")
    data._processed.cache_clear()
    rows = client.get("/api/facilities", params={"limit": 500}).json()
    assert len(rows) > 300
    assert all(r["label"] in {"High", "Watch", "Low", None} for r in rows)
    fac = client.get(f"/api/facility/{rows[0]['ccn']}").json()
    assert fac["state_curve"]


WINDOW = "in the 14 days through the day before past inspections ended"


def test_window_wording_matches_web_and_never_says_before_inspections():
    from api import voice
    for text in (explain_mod.template(FAC), explain_mod.SYSTEM_PROMPT, voice.INSTRUCTIONS):
        assert WINDOW in " ".join(text.split())
        assert "weeks before past inspections" not in text
    # A faithful Grok reply that quotes the window keeps its "14".
    reply = f"Sample Harbor: nurse hours per resident {WINDOW} were 10.8% higher (range 4.9% to 16.2%)."
    assert explain_mod.passes_guardrails(reply, explain_mod.facts_for(FAC))


def test_backlog_matches_schedule_forced():
    """Every home the schedule forces is overdue in /backlog, and vice versa."""
    b = client.get("/api/backlog", headers=REG)
    assert b.status_code == 200 and b.headers["X-Data-Source"].startswith("models:")
    body = b.json()
    assert set(body) == {"as_of", "forced_weeks", "homes"}
    homes = body["homes"]
    assert homes and all(set(h) == {"ccn", "weeks_since_last", "forced"} for h in homes)
    assert all(h["forced"] == (h["weeks_since_last"] >= body["forced_weeks"]) for h in homes)
    s = client.post("/api/schedule", json={"month": "2026-08", "capacity": 22, "seed": 1}, headers=REG).json()
    assert {p["ccn"] for p in s["probs"] if p["forced"]} == {h["ccn"] for h in homes if h["forced"]}
