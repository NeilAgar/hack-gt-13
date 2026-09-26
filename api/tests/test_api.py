import httpx
import pytest
from fastapi.testclient import TestClient

from api import explain as explain_mod
from api.main import app

client = TestClient(app)
REG = {"X-Demo-Role": "regulator"}
TIMING_KEYS = {"p_next_60d", "p_survey_week", "weeks_since_last", "next_survey", "predictability"}


def keys(obj):
    if isinstance(obj, dict):
        return set(obj) | set().union(*(keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(keys(v) for v in obj)) if obj else set()
    return set()


def test_facilities_contract_fields():
    rows = client.get("/api/facilities").json()
    assert rows
    expected = {"ccn", "name", "city", "lat", "lon", "overall_star", "staffing_star",
                "score_pct", "ci_low", "ci_high", "label", "trophy_flag"}
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
    ("get", "/api/trophy", None),
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
        assert s["month"] == "2026-11" and s["capacity"] == k and len(s["selected"]) == k
        assert abs(sum(p["prob"] for p in s["probs"]) - k) < 1e-3
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
    data.simulate.cache_clear()


def test_trophy_still_labelled_fixtures():
    assert client.get("/api/trophy", headers=REG).headers["X-Data-Source"] == "fixtures"


def test_schedule_capacity_above_eligible_pool_is_consistent():
    s = client.post("/api/schedule", json={"month": "2026-10", "capacity": 1000, "seed": 1}, headers=REG).json()
    assert s["capacity"] == len(s["selected"]) < 1000


def test_schedule_rejects_negative_seed():
    r = client.post("/api/schedule", json={"month": "2026-10", "capacity": 3, "seed": -1}, headers=REG)
    assert r.status_code == 422


def test_predictability_comes_from_models_not_file():
    import json
    from api import data
    rows = client.get("/api/predictability", headers=REG).json()
    assert len(rows) == len(data._models()["facilities"]) and set(rows[0]) == {"ccn", "name", "p_next_60d"}
    assert rows == sorted(rows, key=lambda r: (-r["p_next_60d"], r["ccn"]))
    on_disk = data.ROOT / "data" / "processed" / "predictability.json"
    if on_disk.exists():  # same inputs as `make models`; the hazard fit can differ slightly across library versions
        disk = {r["ccn"]: r["p_next_60d"] for r in json.loads(on_disk.read_text())}
        assert set(disk) == {r["ccn"] for r in rows}
        assert all(abs(r["p_next_60d"] - disk[r["ccn"]]) < 1e-2 for r in rows)
