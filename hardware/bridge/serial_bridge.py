#!/usr/bin/env python3
"""USB serial → API bridge for a Call Clock.

    python hardware/bridge/serial_bridge.py --port auto --api http://localhost:8000
    python hardware/bridge/serial_bridge.py --port /dev/ttyUSB0 --dry-run      # print only

Works with the ESP32 and the Arduino Nano builds. On connect it waits for the board's boot line, sends
the time sync ({"cmd":"time","epoch":…,"tz_offset":…}) and asks the device to `dump` its stored log
(backfill; the API is idempotent on (device_id, seq)). Every EVT/LOG line is appended to
hardware/logs/<device>.jsonl and POSTed to /api/bedside in order, retrying with backoff.
Anything you type is forwarded to the device (e.g. `cal on`, `status`).
"""
import argparse
import json
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "hardware" / "logs"
USB_IDS = {(0x10C4, 0xEA60): "CP210x", (0x1A86, 0x7523): "CH340", (0x1A86, 0x55D4): "CH9102",
           (0x303A, 0x1001): "ESP32-S3 USB", (0x0403, 0x6001): "FTDI (genuine Nano)"}
RESYNC_S = 600  # clone Nanos run on a ceramic resonator (up to ~0.5% fast/slow): re-sync often
C = {"call": "\033[1;33m", "arrived": "\033[1;32m", "noentry": "\033[1;31m", "dim": "\033[2m",
     "err": "\033[31m", "off": "\033[0m"}


def find_port(required=True):
    ports = list(list_ports.comports())
    for p in ports:
        if (p.vid, p.pid) in USB_IDS:
            return p.device, USB_IDS[(p.vid, p.pid)]
    for p in ports:
        desc = f"{p.description} {p.manufacturer}".lower()
        if any(k in desc for k in ("cp210", "ch340", "ch910", "ft232", "usb serial", "uart")):
            return p.device, p.description
    if not required:
        return None, ""
    sys.exit("No CP210x/CH340/FTDI serial port found. Plug in the board or pass --port. Seen: "
             + (", ".join(p.device for p in ports) or "none"))


def describe(ev):
    w = ev.get("wait_s")
    wait = "" if w is None else f" after {int(w // 60)}:{w % 60:04.1f}"
    kind = ev.get("event")
    if kind == "call_on":
        return C["call"], f"CALL      {ev.get('call_id')}"
    if kind == "entry":
        return C["arrived"], f"ARRIVED{wait}"
    if kind in ("cancel", "timeout") and ev.get("no_entry"):
        return C["noentry"], f"NO-ENTRY  {kind} with no one entering"
    return C["dim"], f"{kind}{wait}"


class Uploader(threading.Thread):
    """Posts events strictly in order; retries with exponential backoff (1 s → 30 s)."""

    def __init__(self, api, dry_run):
        super().__init__(daemon=True)
        base = api.rstrip("/")
        self.url = (base if base.endswith("/api") else base + "/api") + "/bedside"
        self.dry_run = dry_run
        self.q = queue.Queue()

    def run(self):
        while True:
            ev = self.q.get()
            if self.dry_run:
                continue
            delay = 1.0
            while True:
                try:
                    r = requests.post(self.url, json=ev, timeout=5)
                    r.raise_for_status()
                    res = r.json()
                    if not res.get("verified"):
                        print(f"{C['err']}  server: seq {ev.get('seq')} NOT verified: {res.get('reason')}{C['off']}")
                    break
                except (requests.RequestException, ValueError) as e:
                    print(f"{C['dim']}  API not reachable ({type(e).__name__}); retry seq {ev.get('seq')} in {delay:.0f}s{C['off']}")
                    time.sleep(delay)
                    delay = min(delay * 2, 30)


class LocalLog:
    """hardware/logs/<device>.jsonl, one line per (device, seq)."""

    def __init__(self):
        self.seen = {}

    def append(self, ev):
        dev = ev.get("device_id", "unknown")
        path = LOG_DIR / f"{dev}.jsonl"
        if dev not in self.seen:
            self.seen[dev] = set()
            if path.exists():
                for line in path.read_text().splitlines():
                    try:
                        self.seen[dev].add(json.loads(line)["seq"])
                    except (ValueError, KeyError):
                        pass
        if ev.get("seq") in self.seen[dev]:
            return False
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        self.seen[dev].add(ev.get("seq"))
        return True


def send(ser, text):
    ser.write((text.strip() + "\n").encode())


def local_utc_offset_s():
    """Seconds east of UTC right now (e.g. -14400 for EDT). The Nano has no timezone rules."""
    return int(datetime.now().astimezone().utcoffset().total_seconds())


def time_sync(ser):
    send(ser, json.dumps({"cmd": "time", "epoch": int(time.time()), "tz_offset": local_utc_offset_s()}))


def wait_for_boot(ser, timeout=6.0):
    """Opening the port resets most boards. Wait for the boot line before talking: the Nano replays its
    EEPROM log at boot and has only a 64-byte receive buffer. Returns the lines seen."""
    seen, buf, deadline = [], b"", time.time() + timeout
    while time.time() < deadline:
        buf += ser.read(256)
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("utf-8", "replace").strip()
            if line:
                seen.append(line)
            if line.startswith("DBG boot Call Clock"):
                time.sleep(0.2)
                return seen
    return seen  # no boot line (board didn't reset, e.g. native USB): carry on


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="auto")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--dry-run", action="store_true", help="print only; don't POST")
    ap.add_argument("--no-backfill", action="store_true", help="don't ask the device to dump its stored log")
    ap.add_argument("--quiet-dbg", action="store_true", help="hide DBG lines")
    a = ap.parse_args(argv)

    port, kind = find_port() if a.port == "auto" else (a.port, "")
    print(f"{C['dim']}Call Clock bridge: {port} {kind} @ {a.baud} → {'(dry run)' if a.dry_run else a.api}{C['off']}")

    up = Uploader(a.api, a.dry_run)
    up.start()
    log = LocalLog()
    conn = {"ser": None}

    def connect(port):
        ser = serial.Serial(port, a.baud, timeout=0.2)
        for line in wait_for_boot(ser):
            print(f"{C['dim']}{line}{C['off']}")
        time_sync(ser)
        if not a.no_backfill:
            send(ser, "dump")  # anything recorded while we were away comes back (server ignores duplicates)
        conn["ser"] = ser
        return ser

    def stdin_forwarder():
        for line in sys.stdin:
            if conn["ser"] is not None:
                try:
                    send(conn["ser"], line)
                except (serial.SerialException, OSError):
                    pass

    threading.Thread(target=stdin_forwarder, daemon=True).start()

    try:
        while True:
            try:
                ser = connect(port)
                read_loop(ser, a, up, log)
            except (serial.SerialException, OSError) as e:
                conn["ser"] = None
                print(f"{C['err']}device disconnected ({type(e).__name__}); reconnecting… (events are kept on the device){C['off']}")
                time.sleep(2)
                while True:  # wait for the board to come back (auto mode also finds a new port name)
                    if a.port == "auto":
                        found, _ = find_port(required=False)
                        if found:
                            port = found
                            break
                    elif Path(port).exists():
                        break
                    time.sleep(1)
    except KeyboardInterrupt:
        pending = up.q.qsize()
        if pending:
            print(f"\n{pending} event(s) not yet uploaded; they are in hardware/logs/ and the device will re-send them on the next dump.")
    finally:
        if conn["ser"] is not None:
            conn["ser"].close()


def read_loop(ser, a, up, log):
    """Reads lines until the port errors out (raises SerialException/OSError)."""
    last_sync = time.time()
    buf = b""
    while True:
        if time.time() - last_sync > RESYNC_S:  # keep the device clock honest
            time_sync(ser)
            last_sync = time.time()
        chunk = ser.read(512)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith(("EVT ", "LOG ")):
                try:
                    ev = json.loads(line[4:])
                except ValueError:
                    print(f"{C['err']}unparseable event line: {line[:120]}{C['off']}")
                    continue
                new = log.append(ev)
                if line.startswith("EVT "):
                    colour, text = describe(ev)
                    print(f"{colour}{ev.get('ts') or '(no clock)'}  {ev.get('device_id')} seq {ev.get('seq'):>4}  {text}{C['off']}")
                elif new:
                    print(f"{C['dim']}backfill seq {ev.get('seq')}{C['off']}")
                up.q.put(ev)
            elif line.startswith("DBG "):
                if not a.quiet_dbg:
                    print(f"{C['dim']}{line}{C['off']}")
            elif line:
                print(f"{C['dim']}{line}{C['off']}")


if __name__ == "__main__":
    main()
