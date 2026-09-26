#!/usr/bin/env python3
"""Pretend to be a Call Clock: emit realistic, signed events to the API with no hardware.

Interactive (keys, no Enter needed):  c = call light on   e = someone entered   x = cancel   q = quit
    python hardware/sim/simulate_device.py
Scripted 3-call demo (21 s arrival, 45 s arrival, cancelled with no one entering):
    python hardware/sim/simulate_device.py --script demo
    python hardware/sim/simulate_device.py --script demo --speed 20          # 20x faster
    python hardware/sim/simulate_device.py --script demo --speed 1000 --no-api --out /tmp/demo.jsonl

Events use the same format, hash chain and HMAC as the firmware, and are marked synthetic:true
(they are not bedside measurements). The chain resumes from the API (or the local log) so repeated
runs keep one valid chain per device.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hardware.eventlog import GENESIS, DeviceChain, iso_local, is_night, load_keys, read_jsonl  # noqa: E402

TZ = ZoneInfo("America/New_York")
LOG_DIR = ROOT / "hardware" / "logs"
C = {"call": "\033[33m", "arrived": "\033[32m", "noentry": "\033[31m", "dim": "\033[2m", "off": "\033[0m"}


def api_base(api):
    base = api.rstrip("/")
    return base if base.endswith("/api") else base + "/api"


def post(api, events, retries=3):
    body = json.dumps(events if len(events) != 1 else events[0]).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{api_base(api)}/bedside", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError) as e:
            if attempt == retries - 1:
                print(f"{C['dim']}  (API unreachable: {e}; event kept in the local log){C['off']}")
                return None
            time.sleep(0.5 * 2 ** attempt)


def api_head(api, device):
    """(next_seq, prev_hash) from the server's copy of this device's chain, or None."""
    try:
        with urllib.request.urlopen(f"{api_base(api)}/bedside/events?device_id={device}", timeout=3) as r:
            evs = json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not evs:
        return 1, GENESIS
    last = max(evs, key=lambda e: e["seq"])
    return last["seq"] + 1, last["hash"]


def local_head(path):
    if not path.exists():
        return None
    evs = read_jsonl(path)
    if not evs:
        return None
    last = max(evs, key=lambda e: e["seq"])
    return last["seq"] + 1, last["hash"]


class SimDevice:
    """Same state machine as firmware/src/call_clock.cpp, driven by key presses or a script."""

    def __init__(self, chain, out_path, api, speed):
        self.chain, self.out_path, self.api, self.speed = chain, out_path, api, speed
        self.nonce = f"{int(time.time()) & 0xFFFF:04x}"
        self.counter = 0
        self.state = "IDLE"
        self.call_ms = 0
        self.wait_s = None
        self.t0_wall = datetime.now(TZ)
        self.t0_mono = time.monotonic()
        self.sim_offset = 0.0  # scripted mode advances this instead of waiting on the wall clock

    def now(self):
        """(datetime, ms since 'boot'). Scripted runs use simulated time so --speed keeps real durations."""
        elapsed = self.sim_offset if self.speed != 1 else time.monotonic() - self.t0_mono
        return self.t0_wall + timedelta(seconds=elapsed), int(elapsed * 1000) + 60_000

    def sleep(self, seconds):
        self.sim_offset += seconds
        time.sleep(seconds / self.speed)
        if self.speed == 1:
            self.sim_offset = time.monotonic() - self.t0_mono

    def _emit(self, event, **kw):
        dt, ms = self.now()
        ev = self.chain.emit(call_id=f"{self.nonce}-{self.counter:04d}", event=event, ts=iso_local(dt), ms=ms,
                             night=is_night(dt), **kw)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with self.out_path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        res = post(self.api, [ev]) if self.api else None
        tag = "" if res is None else ("  ✅ verified" if res.get("verified") else f"  ❌ {res.get('reason')}")
        wait = "" if ev["wait_s"] is None else f" after {int(ev['wait_s'] // 60)}:{ev['wait_s'] % 60:04.1f}"
        colour = {"call_on": "call", "entry": "arrived"}.get(event, "noentry" if ev["no_entry"] else "dim")
        label = {"call_on": "CALL", "entry": "ARRIVED", "timeout": "TIMEOUT"}.get(
            event, "NO-ENTRY cancel" if ev["no_entry"] else "cancel")
        print(f"{C[colour]}{ev['ts']}  seq {ev['seq']:>4}  {label}{wait}{C['off']}{tag}")
        return ev

    def call(self):
        if self.state != "IDLE":
            return print(f"{C['dim']}  (a call is already on){C['off']}")
        self.counter += 1
        self.state, self.wait_s = "CALLING", None
        self.call_ms = self.now()[1]
        self._emit("call_on")

    def entry(self):
        if self.state != "CALLING":
            return print(f"{C['dim']}  (entry ignored: {'no call on' if self.state == 'IDLE' else 'already arrived'}){C['off']}")
        self.wait_s = (self.now()[1] - self.call_ms) / 1000
        self.state = "ATTENDED"
        self._emit("entry", wait_s=self.wait_s)

    def cancel(self):
        if self.state == "IDLE":
            return print(f"{C['dim']}  (no call to cancel){C['off']}")
        no_entry = self.state == "CALLING"
        self.state = "IDLE"
        self._emit("cancel", wait_s=self.wait_s, no_entry=no_entry)


def run_demo(dev):
    print("Demo: 3 calls — arrival after 21 s, arrival after 45 s, cancelled with no one entering.")
    for wait, then in ((21, 6), (45, 5), (None, 12)):
        dev.call()
        if wait is None:
            dev.sleep(then)
        else:
            dev.sleep(wait)
            dev.entry()
            dev.sleep(then)
        dev.cancel()
        dev.sleep(5)


def run_interactive(dev):
    print("Keys: c = call light on, e = someone entered, x = cancel, q = quit")
    if not sys.stdin.isatty():
        for line in sys.stdin:
            for ch in line.strip():
                if ch == "q":
                    return
                {"c": dev.call, "e": dev.entry, "x": dev.cancel}.get(ch, lambda: None)()
        return
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1).lower()
            if ch in ("q", "\x03", "\x04"):
                return
            {"c": dev.call, "e": dev.entry, "x": dev.cancel}.get(ch, lambda: None)()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--no-api", action="store_true", help="don't POST; only write the local log")
    ap.add_argument("--device", default="sim-dev")
    ap.add_argument("--ccn", default="115999")
    ap.add_argument("--script", choices=["demo"], help="play a scripted scenario instead of keys")
    ap.add_argument("--speed", type=float, default=1.0, help="time compression for --script (wait_s unchanged)")
    ap.add_argument("--out", help="log file (default hardware/logs/<device>.jsonl). A fresh --out starts a new chain.")
    ap.add_argument("--keys")
    a = ap.parse_args(argv)

    keys = load_keys(a.keys)
    if a.device not in keys:
        sys.exit(f"No key for {a.device}. Add it to hardware/keys/devices.json.")
    api = None if a.no_api else a.api
    out = Path(a.out) if a.out else LOG_DIR / f"{a.device}.jsonl"
    head = (api_head(api, a.device) if api else None) or local_head(out) or (1, GENESIS)
    chain = DeviceChain(a.device, a.ccn, keys[a.device], synthetic=True, next_seq=head[0], prev_hash=head[1])
    print(f"{C['dim']}device {a.device} ccn {a.ccn} next seq {head[0]} → {api or 'local only'} + {out}{C['off']}")
    dev = SimDevice(chain, out, api, a.speed if a.script else 1.0)
    try:
        run_demo(dev) if a.script == "demo" else run_interactive(dev)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
