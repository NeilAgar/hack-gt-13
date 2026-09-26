#!/usr/bin/env python3
"""Verify a Call Clock log: hash chain, HMAC signatures and seq continuity.

    python hardware/tools/verify_log.py hardware/logs/cc-01.jsonl
    python hardware/tools/verify_log.py --api http://localhost:8000 --device cc-01

Prints ✅ with the event count, or ❌ with the first bad seq and why (hash mismatch / bad sig /
chain break / seq gap). Exit code 0 = verified, 1 = altered or unverifiable.
Tamper-EVIDENT, not tamper-proof: anyone holding the device key could forge a whole new chain.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hardware.eventlog import load_keys, read_jsonl, verify_chain  # noqa: E402


def fetch_events(api: str, device: str) -> list[dict]:
    base = api.rstrip("/")
    if not base.endswith("/api"):
        base += "/api"
    with urllib.request.urlopen(f"{base}/bedside/events?device_id={device}", timeout=10) as r:
        return json.load(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="JSONL log (EVT/LOG prefixes are fine)")
    ap.add_argument("--api", help="API base, e.g. http://localhost:8000")
    ap.add_argument("--device", help="device_id to fetch from the API")
    ap.add_argument("--keys", help="devices.json (default: CALLCLOCK_KEYS, keys/devices.json, then the example keys)")
    a = ap.parse_args(argv)

    if a.api:
        if not a.device:
            ap.error("--api needs --device")
        events, source, partial = fetch_events(a.api, a.device), f"{a.api} device {a.device}", False
    elif a.file:
        events, source, partial = read_jsonl(a.file), a.file, True
    else:
        ap.error("give a file or --api URL --device ID")

    if not events:
        print(f"❌ no events in {source}")
        return 1
    events.sort(key=lambda e: (e.get("device_id", ""), e.get("seq", 0)))
    res = verify_chain(events, load_keys(a.keys), allow_partial_start=partial)
    devices = sorted({e.get("device_id") for e in events})
    if res["ok"]:
        first = events[0].get("seq")
        note = f" (file starts mid-chain at seq {first}; earlier events were cleared locally)" if partial and first != 1 else ""
        print(f"✅ log verified: {res['n']} events, device(s) {', '.join(devices)}{note}")
        return 0
    print(f"❌ log altered: first bad event is seq {res['first_bad_seq']} on {res['device_id']}: {res['reason']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
