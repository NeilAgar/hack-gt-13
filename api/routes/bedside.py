"""Call Clock routes ("Measured at the bedside"). Contract addition v1.1 "Bedside".

POST /api/bedside                    one event or a list; verified server-side, stored either way
GET  /api/facility/{ccn}/bedside     stats for the facility panel (synthetic excluded unless asked)
GET  /api/bedside/stream             Server-Sent Events: every new event, instantly (live timer)
GET  /api/bedside/verify?device_id=  re-verify a device's whole stored chain
GET  /api/bedside/events?device_id=  a device's raw signed events (for verify_log.py / resuming a chain)

Wording: "time until someone arrived", never "time to help". Nothing here predicts inspection timing.
"""
import asyncio
import json
import time

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api import bedside_store as store
from hardware.eventlog import load_keys

router = APIRouter(prefix="/api", tags=["bedside"])


class Broker:
    """In-process fan-out of new events to SSE subscribers."""

    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=256)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q):
        self.subscribers.discard(q)

    def publish(self, row: dict):
        for q in list(self.subscribers):
            try:
                q.put_nowait(row)
            except asyncio.QueueFull:
                pass  # a stalled client misses events; it re-syncs from the backlog on reconnect


broker = Broker()


@router.post("/bedside")
async def post_bedside(body: dict | list = Body(...)):
    events = body if isinstance(body, list) else [body]
    if not events:
        raise HTTPException(422, "empty list")
    keys = load_keys()
    results = []
    for ev in events:
        res = store.ingest(ev, keys)
        if res["row"] is not None:
            broker.publish(res["row"])
        results.append({k: res[k] for k in ("accepted", "verified", "reason", "duplicate")}
                       | {"device_id": ev.get("device_id") if isinstance(ev, dict) else None,
                          "seq": ev.get("seq") if isinstance(ev, dict) else None})
    if isinstance(body, dict):
        return results[0]
    first_bad = next((r["reason"] for r in results if not r["verified"]), None)
    return {"accepted": sum(r["accepted"] for r in results), "verified": all(r["verified"] for r in results),
            "reason": first_bad, "results": results}


@router.get("/facility/{ccn}/bedside")
def facility_bedside(ccn: str, include_synthetic: bool = False):
    return store.facility_stats(ccn, include_synthetic)


@router.get("/bedside/verify")
def verify(device_id: str | None = None):
    if device_id:
        return store.verify_device(device_id)
    return [store.verify_device(d) for d in store.devices()]


@router.get("/bedside/events")
def events(device_id: str = Query(...)):
    return store.events_for_device(device_id)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/bedside/stream")
async def stream(request: Request, ccn: str | None = None, backlog: int = Query(10, ge=0, le=100)):
    """Each message carries server_now_ms so the client can correct for clock skew and keep ticking."""
    q = broker.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            for row in store.recent(backlog, ccn):
                yield _sse("bedside", {**row, "backlog": True, "server_now_ms": int(time.time() * 1000)})
            yield _sse("ping", {"server_now_ms": int(time.time() * 1000)})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    row = await asyncio.wait_for(q.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield _sse("ping", {"server_now_ms": int(time.time() * 1000)})
                    continue
                if ccn and row["ccn"] != ccn:
                    continue
                yield _sse("bedside", {**row, "backlog": False, "server_now_ms": int(time.time() * 1000)})
        finally:
            broker.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
