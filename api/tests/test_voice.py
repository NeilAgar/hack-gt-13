import httpx
import pytest
from fastapi.testclient import TestClient

from api import data, voice
from api.main import app

client = TestClient(app)
TIMING_KEYS = {"p_next_60d", "p_survey_week", "weeks_since_last", "next_survey", "predictability"}


@pytest.fixture(autouse=True)
def fixture_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "PROCESSED", tmp_path / "empty")
    data._processed.cache_clear()
    yield
    data._processed.cache_clear()


def test_session_without_key_is_503(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    r = client.post("/api/voice/session")
    assert r.status_code == 503 and "XAI_API_KEY" in r.json()["detail"]


def test_session_mints_short_lived_token_and_hides_key(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret-key")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read()
        return httpx.Response(200, json={"value": "ephemeral-123", "expires_at": 1790000000})

    real_client = httpx.Client
    monkeypatch.setattr(voice.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    body = client.post("/api/voice/session").json()
    assert body["token"] == "ephemeral-123" and body["url"] == voice.REALTIME_URL
    assert seen["auth"] == "Bearer secret-key" and b'"seconds":300' in seen["body"].replace(b" ", b"")
    assert "secret-key" not in str(body)
    assert body["session"]["tools"][0]["name"] == "lookup_facility"


def test_xai_failure_is_502(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "k")
    real_client = httpx.Client
    monkeypatch.setattr(voice.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    assert client.post("/api/voice/session").status_code == 502


def test_instructions_carry_the_guardrails():
    text = voice.session_config()["instructions"]
    for rule in ("survey-responsive staffing", "self-reported", "uncertainty range", "Never say or guess when the next inspection"):
        assert rule in text
    assert "lookup_facility" in text


def test_lookup_returns_only_whitelisted_facts():
    body = client.get("/api/voice/lookup", params={"q": "savannah"}).json()
    assert body["matches"] and all(m["city"] == "Savannah" for m in body["matches"])
    allowed = {"ccn", "name", "city", "n_surveys", "score_pct", "ci_low", "ci_high", "label", "overall_star", "staffing_star"}
    for m in body["matches"]:
        assert set(m) <= allowed and not set(m) & TIMING_KEYS


def test_lookup_no_match_and_validation():
    assert client.get("/api/voice/lookup", params={"q": "zzzz nowhere"}).json()["matches"] == []
    assert client.get("/api/voice/lookup", params={"q": "a"}).status_code == 422


def test_voice_page_is_served():
    r = client.get("/voice")
    assert r.status_code == 200 and "Voice line" in r.text and "/api/voice/session" in r.text
    assert "self-reported" in r.text and "w34037" in r.text and "gaming" not in r.text.lower()


def test_lookup_matches_words_not_exact_strings():
    names = [m["name"] for m in voice.lookup("Sample Harbor in Savannah")["matches"]]
    assert names == ["Sample Harbor Health & Rehab"]


def test_partial_match_gives_names_but_no_numbers():
    r = voice.lookup("Sunrise Harbor")  # no such home; "Harbor" alone must not return Sample Harbor's numbers
    assert r["matches"] == [] and r["did_you_mean"] == ["Sample Harbor Health & Rehab"]
    assert "10.8" not in str(r)
