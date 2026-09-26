"""Call Clock ("Measured at the bedside") storage, verification and stats. SQLite at data/bedside.sqlite.

Every event is stored, verified or not: unverified events are flagged with a reason, never dropped.
Idempotent on (device_id, seq). The event format and checks live in hardware/eventlog.py.
Metric wording: "time until someone arrived", never "time to help".
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from hardware.eventlog import check_event, check_link, load_keys, verify_chain

ROOT = Path(__file__).resolve().parent.parent
SURVEYS = ROOT / "data" / "processed" / "surveys.parquet"
SLOW_S = 600  # "over 10 minutes"
DAYS_SINCE_BUCKETS = [(0, 7, "0-7"), (8, 30, "8-30"), (31, 90, "31-90"), (91, 10**6, "91+")]

_lock = threading.Lock()
_ready: set[str] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  device_id TEXT NOT NULL, seq INTEGER NOT NULL, ccn TEXT, call_id TEXT, event TEXT, ts TEXT, ms INTEGER,
  wait_s REAL, no_entry INTEGER, night INTEGER, synthetic INTEGER, prev_hash TEXT, hash TEXT, sig TEXT,
  raw TEXT NOT NULL, verified INTEGER NOT NULL, reason TEXT, received_at REAL NOT NULL,
  PRIMARY KEY (device_id, seq));
CREATE INDEX IF NOT EXISTS events_ccn ON events (ccn);
CREATE TABLE IF NOT EXISTS conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, seq INTEGER, raw TEXT, reason TEXT, received_at REAL);
"""


def db_path() -> Path:
    return Path(os.environ.get("CALLCLOCK_DB", ROOT / "data" / "bedside.sqlite"))


@contextmanager
def _db():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():  # deleted while the API was running (e.g. to reset the demo): recreate the schema
        _ready.discard(str(path))
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if str(path) not in _ready:
            conn.executescript(SCHEMA)
            _ready.add(str(path))
        yield conn
        conn.commit()
    finally:
        conn.close()


def _tri(v):
    return None if v is None else int(bool(v))


def _get(conn, device_id, seq):
    return conn.execute("SELECT * FROM events WHERE device_id=? AND seq=?", (device_id, seq)).fetchone()


def _raw(row) -> dict:
    return json.loads(row["raw"])


def _verify(conn, ev, keys):
    ok, reason = check_event(ev, keys.get(ev.get("device_id")))
    if not ok:
        return False, reason
    seq = ev["seq"]
    if seq == 1:
        return check_link(None, ev)
    prev = _get(conn, ev["device_id"], seq - 1)
    if prev is None:
        return False, f"seq gap: seq {seq - 1} not received yet"
    return check_link(_raw(prev), ev)


def public_row(row) -> dict:
    """What the API and the live stream expose for one stored event."""
    return {"device_id": row["device_id"], "seq": row["seq"], "ccn": row["ccn"], "call_id": row["call_id"],
            "event": row["event"], "ts": row["ts"], "wait_s": row["wait_s"],
            "no_entry": None if row["no_entry"] is None else bool(row["no_entry"]),
            "night": None if row["night"] is None else bool(row["night"]), "synthetic": bool(row["synthetic"]),
            "verified": bool(row["verified"]), "reason": row["reason"],
            "received_at_ms": int(row["received_at"] * 1000)}


def ingest(ev: dict, keys: dict | None = None) -> dict:
    """Store one event. Returns {accepted, verified, reason, duplicate, row}; row is None if not newly stored."""
    keys = load_keys() if keys is None else keys
    device_id, seq = ev.get("device_id") if isinstance(ev, dict) else None, ev.get("seq") if isinstance(ev, dict) else None
    if not isinstance(device_id, str) or not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        return {"accepted": False, "verified": False, "reason": "malformed: needs device_id and seq >= 1",
                "duplicate": False, "row": None}
    now = time.time()
    raw = json.dumps(ev, sort_keys=True)
    with _lock, _db() as conn:
        existing = _get(conn, device_id, seq)
        if existing is not None:
            if existing["hash"] == ev.get("hash") and existing["raw"] == raw:
                return {"accepted": True, "verified": bool(existing["verified"]), "reason": existing["reason"],
                        "duplicate": True, "row": None}
            reason = f"conflict: seq {seq} already stored with a different event"
            conn.execute("INSERT INTO conflicts (device_id, seq, raw, reason, received_at) VALUES (?,?,?,?,?)",
                         (device_id, seq, raw, reason, now))
            return {"accepted": False, "verified": False, "reason": reason, "duplicate": False, "row": None}

        verified, reason = _verify(conn, ev, keys)
        wait = ev.get("wait_s")
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (device_id, seq, str(ev.get("ccn") or ""), ev.get("call_id"), ev.get("event"), ev.get("ts"),
             ev.get("ms") if isinstance(ev.get("ms"), int) else None,
             float(wait) if isinstance(wait, (int, float)) and not isinstance(wait, bool) else None,
             _tri(ev.get("no_entry")), _tri(ev.get("night")), int(bool(ev.get("synthetic"))),
             ev.get("prev_hash"), ev.get("hash"), ev.get("sig"), raw, int(verified), reason, now))
        # An out-of-order arrival may close a gap: re-check the successors that were waiting on it.
        nxt = seq + 1
        while (row := _get(conn, device_id, nxt)) is not None and not row["verified"] \
                and (row["reason"] or "").startswith("seq gap"):
            ok, why = _verify(conn, _raw(row), keys)
            conn.execute("UPDATE events SET verified=?, reason=? WHERE device_id=? AND seq=?",
                         (int(ok), why, device_id, nxt))
            if not ok:
                break
            nxt += 1
        row = _get(conn, device_id, seq)
    return {"accepted": True, "verified": verified, "reason": reason, "duplicate": False, "row": public_row(row)}


def events_for_device(device_id: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute("SELECT raw FROM events WHERE device_id=? ORDER BY seq", (device_id,)).fetchall()
    return [json.loads(r["raw"]) for r in rows]


def devices() -> list[str]:
    with _db() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT device_id FROM events ORDER BY device_id")]


def verify_device(device_id: str) -> dict:
    evs = events_for_device(device_id)
    if not evs:
        return {"device_id": device_id, "ok": False, "n": 0, "first_bad_seq": None, "reason": "no events"}
    res = verify_chain(evs, load_keys())
    return {"device_id": device_id, "ok": res["ok"], "n": res["n"], "first_bad_seq": res["first_bad_seq"],
            "reason": res["reason"]}


def recent(limit=10, ccn: str | None = None) -> list[dict]:
    with _db() as conn:
        q = "SELECT * FROM events" + (" WHERE ccn=?" if ccn else "") + " ORDER BY received_at DESC, seq DESC LIMIT ?"
        rows = conn.execute(q, ((ccn,) if ccn else ()) + (limit,)).fetchall()
    return [public_row(r) for r in reversed(rows)]


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def _event_time(row) -> float:
    if row["ts"]:
        try:
            return datetime.fromisoformat(row["ts"]).timestamp()
        except ValueError:
            pass
    return row["received_at"]


def _calls(rows):
    """Group verified rows into calls keyed by (device_id, call_id)."""
    calls = {}
    for r in rows:
        c = calls.setdefault((r["device_id"], r["call_id"]), {"on": None, "entry": None, "end": None})
        slot = {"call_on": "on", "entry": "entry", "cancel": "end", "timeout": "end"}.get(r["event"])
        if slot and c[slot] is None:
            c[slot] = r
    out = []
    for c in calls.values():
        if c["on"] is None:
            continue  # its call_on was unverified or never arrived; don't guess
        wait = c["entry"]["wait_s"] if c["entry"] else (c["end"]["wait_s"] if c["end"] else None)
        out.append({"wait_s": wait, "night": c["on"]["night"], "no_entry": bool(c["end"] and c["end"]["no_entry"]),
                    "ts": c["on"]["ts"]})
    return out


def _load_surveys(ccn):
    if not SURVEYS.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(SURVEYS)
    except Exception:
        return None
    df = df[df["ccn"].astype(str).str.zfill(6) == ccn]
    if "survey_type" in df:
        df = df[df["survey_type"] == "health_standard"]
    dates = sorted({pd.Timestamp(d).date() for d in df["survey_date"].dropna()})
    return dates or None


def _by_days_since_inspection(ccn, calls):
    """Median wait by days since the most recent PAST standard survey. Never uses predicted timing."""
    dates = _load_surveys(ccn)
    if not dates:
        return None
    buckets = {label: [] for *_, label in DAYS_SINCE_BUCKETS}
    for c in calls:
        if c["wait_s"] is None or not c["ts"]:
            continue
        d = datetime.fromisoformat(c["ts"]).date()
        past = [s for s in dates if s <= d]
        if not past:
            continue
        days = (d - past[-1]).days
        for lo, hi, label in DAYS_SINCE_BUCKETS:
            if lo <= days <= hi:
                buckets[label].append(c["wait_s"])
    return [{"bucket": label, "median_wait_s": _median(buckets[label]), "n": len(buckets[label])}
            for *_, label in DAYS_SINCE_BUCKETS]


def facility_stats(ccn: str, include_synthetic: bool = False) -> dict:
    with _db() as conn:
        all_rows = conn.execute("SELECT * FROM events WHERE ccn=?", (ccn,)).fetchall()
    all_calls = [r for r in all_rows if r["event"] == "call_on"]
    synthetic_share = round(sum(r["synthetic"] for r in all_calls) / len(all_calls), 3) if all_calls else 0.0
    rows = [r for r in all_rows if include_synthetic or not r["synthetic"]]
    verified = [r for r in rows if r["verified"]]
    calls = _calls(verified)  # stats use verified events only; altered ones are counted in n_unverified
    waits = [c["wait_s"] for c in calls if c["wait_s"] is not None]
    recent_rows = sorted(rows, key=lambda r: (_event_time(r), r["seq"]), reverse=True)[:20]
    return {
        "ccn": ccn,
        "n_devices": len({r["device_id"] for r in rows}),
        "n_calls": len(calls),
        "median_wait_s": _median(waits),
        "p_over_10m": round(sum(w > SLOW_S for w in waits) / len(waits), 3) if waits else None,
        "night_median_wait_s": _median([c["wait_s"] for c in calls if c["wait_s"] is not None and c["night"] == 1]),
        "day_median_wait_s": _median([c["wait_s"] for c in calls if c["wait_s"] is not None and c["night"] == 0]),
        "n_no_entry": sum(c["no_entry"] for c in calls),
        "verified_all": all(r["verified"] for r in rows),
        "n_unverified": sum(not r["verified"] for r in rows),
        "synthetic_share": synthetic_share,
        "recent": [public_row(r) for r in recent_rows],
        "by_days_since_inspection": _by_days_since_inspection(ccn, calls),
    }

