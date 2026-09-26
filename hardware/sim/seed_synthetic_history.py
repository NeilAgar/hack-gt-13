#!/usr/bin/env python3
"""Seed 30 days of SYNTHETIC Call Clock history so the bedside panel has something to show.

    python hardware/sim/seed_synthetic_history.py --ccn 115999 --days 30
    python hardware/sim/seed_synthetic_history.py --ccn 115999 --ccn 115998 --out /tmp/seed.jsonl

Every event is synthetic:true and comes from its own device id (sim-01, sim-02, …), signed with that
device's key so the chain verifies. Distribution: day median ≈ 4 min, night median ≈ 11 min,
8% of calls cancelled with no one entering. Deterministic for a given (--end, --seed): re-running the
same day is idempotent on the server. Re-seeding on a later day conflicts with the stored chain;
delete data/bedside.sqlite first (or use a new device id).
"""
import argparse
import json
import math
import random
import sys
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hardware.eventlog import DeviceChain, iso_local, is_night, load_keys  # noqa: E402

TZ = ZoneInfo("America/New_York")
DAY_MEDIAN_S, NIGHT_MEDIAN_S, SIGMA = 240, 660, 0.75
P_NO_ENTRY = 0.08
CALLS_PER_DAY = 9
# Relative call rate by local hour (more calls around meals, bedtime and morning care).
HOUR_WEIGHTS = [2, 1.5, 1.5, 1.5, 2, 3, 5, 7, 7, 6, 5, 6, 7, 6, 5, 5, 6, 7, 7, 6, 6, 5, 4, 3]


def lognormal(rng, median, sigma=SIGMA):
    return median * math.exp(rng.gauss(0, sigma))


def poisson(rng, lam):
    # Knuth; fine for small lambda.
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < l:
            return k
        k += 1


def generate(ccn, device, key, days, end, rng):
    chain = DeviceChain(device, ccn, key, synthetic=True)
    start = datetime.combine(end - timedelta(days=days), time(0, 0), TZ)
    boot = start - timedelta(hours=1)
    nonce = f"{rng.randrange(0x10000):04x}"
    calls = []
    for d in range(days):
        day = start + timedelta(days=d)
        for _ in range(poisson(rng, CALLS_PER_DAY)):
            hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
            calls.append(day + timedelta(hours=hour, seconds=rng.randrange(3600)))
    calls.sort()

    events, busy_until, n = [], start, 0
    for t_on in calls:
        if t_on < busy_until:  # one call at a time per room
            continue
        n += 1
        call_id = f"{nonce}-{n % 10000:04d}"
        night = is_night(t_on)
        timeline = [(t_on, "call_on", {})]
        if rng.random() < P_NO_ENTRY:
            t_off = t_on + timedelta(seconds=lognormal(rng, 150, 0.6))
            timeline.append((t_off, "cancel", {"wait_s": None, "no_entry": True}))
        else:
            wait = max(5.0, lognormal(rng, NIGHT_MEDIAN_S if night else DAY_MEDIAN_S))
            t_in = t_on + timedelta(seconds=wait)
            t_off = t_in + timedelta(seconds=lognormal(rng, 90, 0.5))
            wait = round(wait, 1)
            timeline.append((t_in, "entry", {"wait_s": wait}))
            timeline.append((t_off, "cancel", {"wait_s": wait, "no_entry": False}))
        busy_until = t_off + timedelta(seconds=30)
        for t, kind, kw in timeline:
            if t > datetime.now(TZ):
                break
            ms = int((t - boot).total_seconds() * 1000)
            events.append(chain.emit(call_id=call_id, event=kind, ts=iso_local(t), ms=ms, night=is_night(t),
                                     **kw))
    return events


def post_batches(api, events, batch=250):
    base = api.rstrip("/")
    base = base if base.endswith("/api") else base + "/api"
    bad = 0
    for i in range(0, len(events), batch):
        body = json.dumps(events[i:i + batch]).encode()
        req = urllib.request.Request(f"{base}/bedside", data=body, headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
        bad += sum(1 for x in res.get("results", []) if not x.get("verified"))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ccn", action="append", help="repeatable, up to 3 (default 115999)")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--end", type=date.fromisoformat, default=date.today(), help="last day (default today)")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", help="write JSONL here instead of POSTing to the API")
    ap.add_argument("--keys")
    a = ap.parse_args(argv)

    ccns = a.ccn or ["115999"]
    if len(ccns) > 3:
        sys.exit("At most 3 demo CCNs.")
    keys = load_keys(a.keys)
    all_events = []
    for i, ccn in enumerate(ccns, start=1):
        device = f"sim-{i:02d}"
        if device not in keys:
            sys.exit(f"No key for {device}. Add it to hardware/keys/devices.json.")
        rng = random.Random(f"{a.seed}-{ccn}-{device}-{a.end}")
        evs = generate(ccn, device, keys[device], a.days, a.end, rng)
        n_calls = sum(e["event"] == "call_on" for e in evs)
        n_no = sum(bool(e["no_entry"]) for e in evs if e["event"] == "cancel")
        print(f"{device} → ccn {ccn}: {len(evs)} events, {n_calls} calls, {n_no} cancelled with no one entering")
        all_events += evs

    if a.out:
        Path(a.out).write_text("".join(json.dumps(e) + "\n" for e in all_events))
        print(f"wrote {len(all_events)} SYNTHETIC events to {a.out}")
    else:
        bad = post_batches(a.api, all_events)
        print(f"posted {len(all_events)} SYNTHETIC events to {a.api}" + (f" ({bad} NOT verified!)" if bad else ""))


if __name__ == "__main__":
    main()
