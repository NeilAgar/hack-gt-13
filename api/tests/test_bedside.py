"""Call Clock bedside endpoints: verification on ingest, idempotency, stats math."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from hardware.eventlog import DeviceChain, compute_hash

KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
KEYS = {"t-01": KEY.hex(), "t-02": KEY.hex(), "t-syn": KEY.hex()}
CCN = "115999"

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CALLCLOCK_DB", str(tmp_path / "bedside.sqlite"))
    monkeypatch.setenv("CALLCLOCK_KEYS", json.dumps(KEYS))


def make_calls(device="t-01", calls=(("21.4", False), (None, True)), night=False, synthetic=False, ccn=CCN):
    """calls: (wait_s or None, no_entry). Returns the signed events in order."""
    chain = DeviceChain(device, ccn, KEY, synthetic=synthetic)
    evs, ms, n = [], 10_000, 0
    ts = "2026-09-26T02:00:00-04:00" if night else "2026-09-26T14:00:00-04:00"
    for wait, no_entry in calls:
        n += 1
        cid = f"abcd-{n:04d}"
        evs.append(chain.emit(call_id=cid, event="call_on", ts=ts, ms=ms, night=night))
        if wait is not None:
            evs.append(chain.emit(call_id=cid, event="entry", ts=ts, ms=ms + 1, wait_s=float(wait), night=night))
        evs.append(chain.emit(call_id=cid, event="cancel", ts=ts, ms=ms + 2,
                              wait_s=None if wait is None else float(wait), no_entry=no_entry, night=night))
        ms += 100_000
    return evs


def post(body):
    r = client.post("/api/bedside", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_happy_path_single_and_list():
    evs = make_calls()
    first = post(evs[0])
    assert first["accepted"] is True and first["verified"] is True and first["reason"] is None
    rest = post(evs[1:])
    assert rest["accepted"] == len(evs) - 1 and rest["verified"] is True
    stats = client.get(f"/api/facility/{CCN}/bedside").json()
    assert stats["n_calls"] == 2
    assert stats["median_wait_s"] == 21.4
    assert stats["n_no_entry"] == 1
    assert stats["verified_all"] is True
    assert stats["synthetic_share"] == 0.0
    assert stats["n_devices"] == 1
    assert stats["by_days_since_inspection"] is None  # no surveys.parquet in tests
    assert len(stats["recent"]) == len(evs)
    assert client.get("/api/bedside/verify", params={"device_id": "t-01"}).json()["ok"] is True


def test_tampered_wait_is_stored_but_unverified():
    evs = make_calls(calls=(("21.4", False),))
    evs[1]["wait_s"] = 3.0  # make the home look faster
    res = post(evs)
    assert res["accepted"] == 3  # stored, never silently dropped
    assert res["verified"] is False
    assert "hash mismatch" in res["results"][1]["reason"]
    stats = client.get(f"/api/facility/{CCN}/bedside").json()
    assert stats["verified_all"] is False
    assert stats["n_unverified"] == 1
    assert stats["median_wait_s"] == 21.4  # the altered 3.0 never reaches the stats; cancel's wait is used
    v = client.get("/api/bedside/verify", params={"device_id": "t-01"}).json()
    assert v["ok"] is False and v["first_bad_seq"] == 2


def test_rehashed_tamper_fails_signature():
    evs = make_calls(calls=(("21.4", False),))
    evs[1]["wait_s"] = 3.0
    evs[1]["hash"] = compute_hash(evs[1])
    res = post(evs)
    assert res["results"][1]["reason"] == "bad sig"


def test_unknown_device_flagged():
    evs = make_calls(device="nobody")
    res = post(evs)
    assert res["verified"] is False and "unknown device" in res["reason"]


def test_duplicate_seq_is_idempotent():
    evs = make_calls()
    post(evs)
    again = post(evs[0])
    assert again["accepted"] is True and again["duplicate"] is True and again["verified"] is True
    assert client.get(f"/api/facility/{CCN}/bedside").json()["n_calls"] == 2
    # Same seq, different content: rejected as a conflict (and kept in the conflicts table).
    forged = copy.deepcopy(evs[0])
    forged["ms"] += 1
    res = post(forged)
    assert res["accepted"] is False and "conflict" in res["reason"]


def test_out_of_order_gap_heals():
    evs = make_calls(calls=(("30", False),))
    res = post(evs[2])
    assert res["verified"] is False and "seq gap" in res["reason"]
    post(evs[0])
    post(evs[1])
    assert client.get(f"/api/facility/{CCN}/bedside").json()["verified_all"] is True


def test_stats_math_night_day_and_p_over_10m():
    day = make_calls("t-01", calls=(("60", False), ("120", False), ("700", False), (None, True)))
    night = make_calls("t-02", calls=(("300", False), ("900", False)), night=True)
    post(day + night)
    s = client.get(f"/api/facility/{CCN}/bedside").json()
    assert s["n_devices"] == 2
    assert s["n_calls"] == 6
    assert s["median_wait_s"] == 300.0  # waits 60, 120, 300, 700, 900
    assert s["p_over_10m"] == 0.4  # 700 and 900 of 5 arrivals
    assert s["day_median_wait_s"] == 120.0
    assert s["night_median_wait_s"] == 600.0
    assert s["n_no_entry"] == 1


def test_synthetic_excluded_unless_asked():
    post(make_calls("t-01", calls=(("10", False),)))
    post(make_calls("t-syn", calls=(("500", False), ("500", False), ("500", False)), synthetic=True))
    s = client.get(f"/api/facility/{CCN}/bedside").json()
    assert s["n_calls"] == 1 and s["median_wait_s"] == 10.0
    assert s["synthetic_share"] == 0.75
    s2 = client.get(f"/api/facility/{CCN}/bedside", params={"include_synthetic": "true"}).json()
    assert s2["n_calls"] == 4 and s2["median_wait_s"] == 500.0


def test_events_endpoint_returns_signed_chain():
    evs = make_calls()
    post(evs)
    got = client.get("/api/bedside/events", params={"device_id": "t-01"}).json()
    assert [e["seq"] for e in got] == [e["seq"] for e in evs]
    assert got[0]["hash"] == evs[0]["hash"]


def test_empty_facility():
    s = client.get("/api/facility/000000/bedside").json()
    assert s["n_calls"] == 0 and s["median_wait_s"] is None and s["recent"] == []


def test_no_inspection_timing_leaks():
    post(make_calls())
    body = client.get(f"/api/facility/{CCN}/bedside").text
    for k in ("p_next_60d", "p_survey_week", "weeks_since_last", "next_survey"):
        assert k not in body
