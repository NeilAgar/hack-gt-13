"""Event format, chain and verifier. Run: python -m pytest hardware/tests"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hardware.eventlog import (GENESIS, DeviceChain, canonical, check_event, compute_hash, sign_event,
                               verify_chain)

ROOT = Path(__file__).resolve().parents[2]

# CROSS-LANGUAGE TEST VECTOR: identical to test_cross_language_vector() in
# hardware/firmware/test/test_call_clock/test_main.cpp. If you change the format, change both.
VEC_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
VEC_FIELDS = dict(seq=12, device_id="cc-01", ccn="115999", call_id="a1b2-0007", event="entry",
                  ts="2026-09-26T14:03:22-04:00", ms=1234567, wait_s=21.4, no_entry=None, night=False,
                  synthetic=False, prev_hash=GENESIS)
VEC_CANONICAL = ('{"call_id":"a1b2-0007","ccn":"115999","device_id":"cc-01","event":"entry",'
                 '"ms":1234567,"night":false,"no_entry":null,'
                 '"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000",'
                 '"seq":12,"synthetic":false,"ts":"2026-09-26T14:03:22-04:00","v":1,"wait_s":21.4}')
VEC_HASH = "43fdb7fcba627e8662e1db8c2b3debd00c2aa4c80ddd6eb483e79bdaabe5934a"
VEC_SIG = "5cd1a4bc9bac4b3f8f72824b8ec0fe926aad8a8c6ea1030f1cea85eca35c274e"


def test_cross_language_vector():
    ev = sign_event(VEC_FIELDS, VEC_KEY)
    assert canonical(ev) == VEC_CANONICAL
    assert ev["hash"] == VEC_HASH
    assert ev["sig"] == VEC_SIG


def test_vector_matches_firmware_source():
    """Guard against someone updating only one side of the vector."""
    cpp = (ROOT / "hardware/firmware/test/test_call_clock/test_main.cpp").read_text()
    assert VEC_HASH in cpp and VEC_SIG in cpp


def test_canonical_floats_and_parsed_json_roundtrip():
    ev = sign_event({**VEC_FIELDS, "wait_s": 21}, VEC_KEY)
    assert canonical(ev).endswith('"wait_s":21.0}')
    line = json.dumps(ev)  # what goes over the wire
    back = json.loads(line)
    ok, reason = check_event(back, VEC_KEY)
    assert ok, reason


def _chain(n=5):
    dev = DeviceChain("cc-01", "115999", VEC_KEY, synthetic=False)
    return [dev.emit(call_id="beef-0001", event="call_on", ts=None, ms=1000 * i, night=None) for i in range(n)]


def test_chain_verifies():
    evs = _chain()
    assert evs[0]["seq"] == 1 and evs[0]["prev_hash"] == GENESIS
    assert verify_chain(evs, {"cc-01": VEC_KEY})["ok"]


@pytest.mark.parametrize("mutate, reason", [
    (lambda evs: evs[2].update(wait_s=3.0), "hash mismatch"),
    (lambda evs: (evs[2].update(wait_s=3.0), evs[2].update(hash=compute_hash(evs[2]))), "bad sig"),
    (lambda evs: evs.pop(2), "seq gap"),
    (lambda evs: evs[3].update(prev_hash="f" * 64), "hash mismatch"),
])
def test_tampering_detected(mutate, reason):
    evs = copy.deepcopy(_chain())
    mutate(evs)
    res = verify_chain(evs, {"cc-01": VEC_KEY})
    assert not res["ok"]
    assert reason in res["reason"]


def test_resigned_chain_break():
    """Re-signing with the right key but splicing out an event still breaks the chain."""
    evs = _chain()
    del evs[2]
    for i, e in enumerate(evs):
        e["seq"] = i + 1
    for e in evs[2:]:
        e["hash"] = compute_hash(e)
    res = verify_chain(evs, {"cc-01": VEC_KEY})
    assert not res["ok"]


def test_partial_start_allowed_for_cleared_logs():
    evs = _chain()[2:]
    assert not verify_chain(evs, {"cc-01": VEC_KEY})["ok"]
    assert verify_chain(evs, {"cc-01": VEC_KEY}, allow_partial_start=True)["ok"]


def test_unknown_device():
    res = verify_chain(_chain(), {})
    assert not res["ok"] and "unknown device" in res["reason"]


def test_tamper_demo_script(tmp_path):
    """End to end: simulator writes a signed log, the verifier passes it, tamper_demo.sh shows ❌."""
    out = subprocess.run(["bash", str(ROOT / "hardware/tools/tamper_demo.sh")], capture_output=True, text=True,
                         cwd=ROOT, env={"TMPDIR": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin",
                                        "PYTHON": sys.executable})
    assert out.returncode == 0, out.stdout + out.stderr
    assert "✅" in out.stdout and "❌" in out.stdout
