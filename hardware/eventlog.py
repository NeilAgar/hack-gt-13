"""Call Clock event format, hash chain and signature, the Python twin of firmware/src/event_log.cpp.

    canonical = JSON of every field except "hash" and "sig", keys sorted, no spaces,
                wait_s with exactly 1 decimal, null as null
    hash      = SHA256(prev_hash_hex + canonical)          genesis prev_hash = 64 zeros
    sig       = HMAC_SHA256(device_key_bytes, hash_hex)

Tamper-EVIDENT, not tamper-proof: whoever holds the device key can forge a chain.
Used by the API (server-side verification), the simulator, the seeder, the bridge and verify_log.py.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENESIS = "0" * 64
SCHEMA_VERSION = 1
EVENT_TYPES = ("call_on", "entry", "cancel", "timeout")
# Sorted field order of the canonical string. Keep in sync with cc_canonical() in event_log.cpp.
CANONICAL_KEYS = ("call_id", "ccn", "device_id", "event", "ms", "night", "no_entry", "prev_hash",
                  "seq", "synthetic", "ts", "v", "wait_s")
INT_FIELDS = {"ms", "seq", "v"}
FLOAT1_FIELDS = {"wait_s"}
BOOL_FIELDS = {"night", "no_entry", "synthetic"}
STR_FIELDS = {"call_id", "ccn", "device_id", "event", "prev_hash", "ts"}


def _value(key, val):
    if val is None:
        return "null"
    if key in BOOL_FIELDS:
        if not isinstance(val, bool):
            raise ValueError(f"{key} must be a bool or null")
        return "true" if val else "false"
    if key in FLOAT1_FIELDS:
        # Decisecond integer arithmetic, so 21.4 is always "21.4" (same as the firmware's %ld.%ld).
        ds = round(float(val) * 10)
        if ds < 0:
            raise ValueError(f"{key} must be >= 0")
        return f"{ds // 10}.{ds % 10}"
    if key in INT_FIELDS:
        if isinstance(val, bool) or int(val) != val:
            raise ValueError(f"{key} must be an integer")
        return str(int(val))
    if key in STR_FIELDS:
        return json.dumps(str(val), ensure_ascii=True)
    raise KeyError(key)


def canonical(event: dict) -> str:
    missing = [k for k in CANONICAL_KEYS if k not in event]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    return "{" + ",".join(f'"{k}":{_value(k, event[k])}' for k in CANONICAL_KEYS) + "}"


def compute_hash(event: dict) -> str:
    return hashlib.sha256((event["prev_hash"] + canonical(event)).encode("ascii")).hexdigest()


def compute_sig(key: bytes, hash_hex: str) -> str:
    return hmac.new(key, hash_hex.encode("ascii"), hashlib.sha256).hexdigest()


def round_wait(wait_s):
    return None if wait_s is None else round(wait_s * 10) / 10


def sign_event(fields: dict, key: bytes) -> dict:
    """Return a copy of `fields` with v, hash and sig filled in. `fields` needs every canonical key but v."""
    ev = {"v": SCHEMA_VERSION, **fields}
    ev["wait_s"] = round_wait(ev.get("wait_s"))
    ev["hash"] = compute_hash(ev)
    ev["sig"] = compute_sig(key, ev["hash"])
    return {k: ev[k] for k in (*CANONICAL_KEYS, "hash", "sig")}


def check_event(event: dict, key: bytes | None) -> tuple[bool, str | None]:
    """Content checks on one event in isolation: schema, hash, signature. Chain checks are separate."""
    try:
        if event.get("v") != SCHEMA_VERSION:
            return False, f"unsupported version {event.get('v')!r}"
        if event.get("event") not in EVENT_TYPES:
            return False, f"unknown event type {event.get('event')!r}"
        expected = compute_hash(event)
    except (ValueError, KeyError, TypeError) as e:
        return False, f"malformed: {e}"
    if event.get("hash") != expected:
        return False, "hash mismatch (content altered after signing)"
    if key is None:
        return False, f"unknown device {event.get('device_id')!r} (no key)"
    if not hmac.compare_digest(str(event.get("sig", "")), compute_sig(key, expected)):
        return False, "bad sig"
    return True, None


def check_link(prev: dict | None, event: dict) -> tuple[bool, str | None]:
    """Chain checks between an event and its predecessor (None = no predecessor known)."""
    seq = event.get("seq")
    if prev is None:
        if seq == 1 and event.get("prev_hash") != GENESIS:
            return False, "chain break: seq 1 must start from the genesis hash"
        if seq != 1:
            return False, f"seq gap: seq {seq} arrived without seq {seq - 1 if isinstance(seq, int) else '?'}"
        return True, None
    if seq != prev["seq"] + 1:
        return False, f"seq gap: expected {prev['seq'] + 1}, got {seq}"
    if event.get("prev_hash") != prev.get("hash"):
        return False, "chain break: prev_hash does not match the previous event's hash"
    return True, None


def verify_chain(events: list[dict], keys: dict[str, bytes], allow_partial_start: bool = False) -> dict:
    """Verify an ordered list of events from one or more devices.

    Returns {ok, n, first_bad_seq, device_id, reason}. With allow_partial_start, a file that begins
    mid-chain (because the device's local log was cleared) is accepted from its first event on.
    """
    by_dev: dict[str, list[dict]] = {}
    for ev in events:
        by_dev.setdefault(ev.get("device_id", "?"), []).append(ev)
    for dev, evs in by_dev.items():
        prev = None
        for i, ev in enumerate(evs):
            ok, reason = check_event(ev, keys.get(dev))
            if ok:
                if i == 0 and allow_partial_start and ev.get("seq") != 1:
                    pass  # trust the first stored hash as the anchor
                else:
                    ok, reason = check_link(prev, ev)
            if not ok:
                return {"ok": False, "n": len(events), "first_bad_seq": ev.get("seq"), "device_id": dev,
                        "reason": reason}
            prev = ev
    return {"ok": True, "n": len(events), "first_bad_seq": None, "device_id": None, "reason": None}


def load_keys(path: str | os.PathLike | None = None) -> dict[str, bytes]:
    """Device keys {device_id: key bytes}.

    Order: CALLCLOCK_KEYS env (inline JSON or a path) → hardware/keys/devices.json →
    hardware/keys/devices.example.json (public demo keys; fine for the demo, never for real).
    """
    raw = None
    if path:
        raw = Path(path).read_text()
    elif os.environ.get("CALLCLOCK_KEYS"):
        env = os.environ["CALLCLOCK_KEYS"].strip()
        raw = env if env.startswith("{") else Path(env).read_text()
    else:
        for cand in (HERE / "keys" / "devices.json", HERE / "keys" / "devices.example.json"):
            if cand.exists():
                raw = cand.read_text()
                break
    if raw is None:
        return {}
    data = json.loads(raw)
    return {k: bytes.fromhex(v) for k, v in data.items() if not k.startswith("_")}


def iso_local(dt: datetime) -> str:
    """ISO-8601 with a ±HH:MM offset and whole seconds, like the firmware prints."""
    return dt.replace(microsecond=0).isoformat()


def is_night(dt: datetime, start_hour: int = 23, end_hour: int = 7) -> bool:
    return dt.hour >= start_hour or dt.hour < end_hour


def read_jsonl(path) -> list[dict]:
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        for prefix in ("EVT ", "LOG "):
            if line.startswith(prefix):
                line = line[len(prefix):]
        if line:
            out.append(json.loads(line))
    return out


class DeviceChain:
    """Chain head for a software device (simulator, seeder). Mirrors EventChain in the firmware."""

    def __init__(self, device_id: str, ccn: str, key: bytes, synthetic: bool = True,
                 next_seq: int = 1, prev_hash: str = GENESIS):
        self.device_id, self.ccn, self.key, self.synthetic = device_id, ccn, key, synthetic
        self.next_seq, self.prev_hash = next_seq, prev_hash

    def emit(self, *, call_id, event, ts, ms, wait_s=None, no_entry=None, night=None) -> dict:
        ev = sign_event({"seq": self.next_seq, "device_id": self.device_id, "ccn": self.ccn,
                         "call_id": call_id, "event": event, "ts": ts, "ms": int(ms), "wait_s": wait_s,
                         "no_entry": no_entry, "night": night, "synthetic": self.synthetic,
                         "prev_hash": self.prev_hash}, self.key)
        self.next_seq += 1
        self.prev_hash = ev["hash"]
        return ev
