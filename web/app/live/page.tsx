"use client";

import { useEffect, useRef, useState } from "react";

import {
  BEDSIDE_FOOTNOTE,
  bedsideApiBase,
  formatShare,
  formatWait,
  type BedsideEvent,
  type BedsideStats,
} from "@/components/BedsidePanel";
import { UNSCORED_COPY } from "@/lib/format";

/**
 * Full-screen live Call Clock timer for the demo screen.
 *   /live                  facility 115999, demo thresholds (green < 15 s, amber < 30 s, red ≥ 30 s)
 *   /live?ccn=115998       another facility
 *   /live?demo=0           real thresholds (5 min / 10 min)
 * Subscribes to GET /api/bedside/stream (Server-Sent Events). The timer runs from the server's event
 * time plus a skew-corrected client clock, so it keeps ticking between events and after a reload.
 */

type Mode = "idle" | "waiting" | "arrived" | "noentry";

type LiveState = {
  mode: Mode;
  callId: string | null;
  anchorMs: number | null; // server-clock ms when the call light came on
  waitS: number | null;
  synthetic: boolean;
  verified: boolean;
  deviceId: string | null;
};

type FacilityInfo = {
  name: string;
  city?: string;
  score_pct?: number;
  ci_low?: number;
  ci_high?: number;
  label?: string;
  n_surveys?: number;
};

type StreamEvent = BedsideEvent & { backlog: boolean; server_now_ms: number };

const INITIAL: LiveState = {
  mode: "idle",
  callId: null,
  anchorMs: null,
  waitS: null,
  synthetic: false,
  verified: true,
  deviceId: null,
};

const COLORS = {
  green: "#1f8a4c",
  amber: "#d98b0b",
  red: "#c0392b",
  idle: "#0c2f39",
  arrived: "#123f4c",
};

/** When did the call start, on the server's clock? Live events: the moment the server received them
 * (ms precision). Late/backlog events (received > 5 s after the device's own timestamp): the device ts. */
function callAnchor(ev: BedsideEvent): number {
  const tsMs = ev.ts ? Date.parse(ev.ts) : NaN;
  if (Number.isFinite(tsMs) && Math.abs(ev.received_at_ms - tsMs) > 5000) return tsMs;
  return ev.received_at_ms;
}

function reduce(state: LiveState, ev: BedsideEvent): LiveState {
  const base = { synthetic: ev.synthetic, verified: ev.verified, deviceId: ev.device_id };
  switch (ev.event) {
    case "call_on":
      return { ...base, mode: "waiting", callId: ev.call_id, anchorMs: callAnchor(ev), waitS: null };
    case "entry":
      return { ...state, ...base, mode: "arrived", callId: ev.call_id, waitS: ev.wait_s };
    case "cancel":
    case "timeout":
      if (ev.no_entry) return { ...state, ...base, mode: "noentry", callId: ev.call_id, waitS: null };
      return { ...state, ...base, mode: "arrived", callId: ev.call_id, waitS: ev.wait_s ?? state.waitS };
  }
}

function formatClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export default function LivePage() {
  const [ccn, setCcn] = useState<string | null>(null);
  const [thresholds, setThresholds] = useState({ amber: 15, red: 30, demo: true });
  const [live, setLive] = useState<LiveState>(INITIAL);
  const [connected, setConnected] = useState(false);
  const [facility, setFacility] = useState<FacilityInfo | null>(null);
  const [facilityError, setFacilityError] = useState(false);
  const [stats, setStats] = useState<BedsideStats | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const skewRef = useRef(0); // server_now - client_now

  // Read ?ccn= and ?demo= on the client (keeps this page free of Suspense boundaries).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setCcn(params.get("ccn") || "115999");
    if (params.get("demo") === "0") setThresholds({ amber: 300, red: 600, demo: false });
  }, []);

  // Facility name + StaffTrace score for the side column.
  useEffect(() => {
    if (!ccn) return;
    let cancelled = false;
    fetch(`${bedsideApiBase()}/facility/${encodeURIComponent(ccn)}`, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((body: FacilityInfo) => !cancelled && setFacility(body))
      .catch(() => !cancelled && setFacilityError(true));
    return () => {
      cancelled = true;
    };
  }, [ccn]);

  // Bedside summary, refreshed whenever a call finishes.
  const statsKey = live.mode === "waiting" ? "waiting" : `${live.callId}-${live.mode}`;
  useEffect(() => {
    if (!ccn) return;
    let cancelled = false;
    fetch(`${bedsideApiBase()}/facility/${encodeURIComponent(ccn)}/bedside?include_synthetic=true`, {
      cache: "no-store",
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((body: BedsideStats) => !cancelled && setStats(body))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [ccn, statsKey]);

  // The live stream.
  useEffect(() => {
    if (!ccn) return;
    const source = new EventSource(`${bedsideApiBase()}/bedside/stream?ccn=${encodeURIComponent(ccn)}`);
    const onSkew = (serverNow: number) => {
      if (Number.isFinite(serverNow)) skewRef.current = serverNow - Date.now();
    };
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("ping", (msg) => {
      setConnected(true);
      onSkew(JSON.parse((msg as MessageEvent<string>).data).server_now_ms);
    });
    source.addEventListener("bedside", (msg) => {
      const ev = JSON.parse((msg as MessageEvent<string>).data) as StreamEvent;
      onSkew(ev.server_now_ms);
      setLive((prev) => reduce(prev, ev));
    });
    return () => source.close();
  }, [ccn]);

  // Tick. Server time = client clock + skew, so the timer never depends on a new event arriving.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, []);

  const serverNow = now + skewRef.current;
  const elapsedMs = live.mode === "waiting" && live.anchorMs !== null ? serverNow - live.anchorMs : 0;
  const elapsedS = elapsedMs / 1000;

  let background = COLORS.idle;
  let headline = "Waiting for a call…";
  let big: string | null = null;
  if (live.mode === "waiting") {
    background = elapsedS < thresholds.amber ? COLORS.green : elapsedS < thresholds.red ? COLORS.amber : COLORS.red;
    headline = "Call light on — waiting";
    big = formatClock(elapsedMs);
  } else if (live.mode === "arrived") {
    background = COLORS.arrived;
    headline = "Someone arrived after";
    big = formatWait(live.waitS);
  } else if (live.mode === "noentry") {
    background = COLORS.red;
    headline = "Cancelled — no one entered";
  }

  return (
    <div
      className="callclock-live"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 24rem)",
        background,
        color: "#fff",
        fontFamily: '"Segoe UI", "Helvetica Neue", sans-serif',
        transition: "background 400ms ease",
      }}
    >
      <style>{`@media (max-width: 720px) {
        .callclock-live { grid-template-columns: 1fr !important; grid-auto-rows: min-content; overflow-y: auto; }
      }`}</style>
      <main
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          padding: "2rem",
          textAlign: "center",
        }}
      >
        <p style={{ fontSize: "clamp(1.5rem, 3.5vw, 3rem)", margin: 0, fontWeight: 600 }}>{headline}</p>
        {big !== null ? (
          <p
            aria-live="off"
            style={{
              fontSize: "clamp(6rem, 22vw, 22rem)",
              lineHeight: 1,
              margin: "1rem 0",
              fontVariantNumeric: "tabular-nums",
              fontWeight: 700,
            }}
          >
            {big}
          </p>
        ) : live.mode === "noentry" ? (
          <p style={{ fontSize: "clamp(5rem, 16vw, 16rem)", lineHeight: 1, margin: "1rem 0" }}>✕</p>
        ) : null}
        <p style={{ opacity: 0.85, fontSize: "clamp(1rem, 1.6vw, 1.4rem)", maxWidth: "40rem" }}>
          Time until someone arrived, not time to care.
          {live.mode === "waiting"
            ? ` Green under ${formatWait(thresholds.amber)}, amber under ${formatWait(thresholds.red)}, red after.`
            : ""}
        </p>
        {live.deviceId ? (
          <p style={{ opacity: 0.75, fontSize: "0.95rem" }}>
            Device {live.deviceId}
            {live.synthetic ? " · synthetic demo data" : ""}
            {live.verified ? " · ✅ signed event verified" : " · ❌ event failed verification"}
          </p>
        ) : null}
      </main>

      <aside
        style={{
          background: "rgba(0, 0, 0, 0.28)",
          padding: "2rem 1.5rem",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          overflowY: "auto",
        }}
      >
        <div>
          <p style={{ textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.8rem", opacity: 0.8, margin: 0 }}>
            StaffTrace · Call Clock
          </p>
          {facility ? (
            <>
              <h1 style={{ fontSize: "1.6rem", margin: "0.3rem 0" }}>{facility.name}</h1>
              {facility.city ? <p style={{ margin: 0, opacity: 0.85 }}>{facility.city}</p> : null}
            </>
          ) : (
            <h1 style={{ fontSize: "1.6rem", margin: "0.3rem 0" }}>Facility {ccn ?? ""}</h1>
          )}
        </div>

        <section>
          <h2 style={{ fontSize: "1rem", margin: "0 0 0.3rem" }}>Survey-responsive staffing</h2>
          {facility && typeof facility.score_pct === "number" ? (
            <p style={{ margin: 0 }}>
              Nurse hours per resident were <b>{facility.score_pct.toFixed(1)}%</b>{" "}
              {facility.score_pct >= 0 ? "higher" : "lower"} in the 14 days through the day before
              past inspections ended than a month later
              {typeof facility.ci_low === "number" && typeof facility.ci_high === "number"
                ? ` (range ${facility.ci_low.toFixed(1)}–${facility.ci_high.toFixed(1)}%)`
                : ""}
              {facility.label ? `. Staffing Consistency: ${facility.label}.` : "."}
            </p>
          ) : facility ? (
            <p style={{ margin: 0, opacity: 0.85 }}>{UNSCORED_COPY}</p>
          ) : (
            <p style={{ margin: 0, opacity: 0.85 }}>
              {facilityError ? "StaffTrace score unavailable for this facility." : "Loading score…"}
            </p>
          )}
          <p style={{ margin: "0.3rem 0 0", fontSize: "0.8rem", opacity: 0.75 }}>PBJ staffing data is self-reported.</p>
        </section>

        <section>
          <h2 style={{ fontSize: "1rem", margin: "0 0 0.3rem" }}>Measured at the bedside</h2>
          {stats && stats.n_calls > 0 ? (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, lineHeight: 1.7 }}>
              <li>
                Median time until someone arrived: <b>{formatWait(stats.median_wait_s)}</b>
              </li>
              <li>
                Night / day: <b>{formatWait(stats.night_median_wait_s)}</b> / <b>{formatWait(stats.day_median_wait_s)}</b>
              </li>
              <li>
                Cancelled with no one entering: <b>{stats.n_no_entry}</b> of {stats.n_calls}
              </li>
              <li>{stats.verified_all ? "✅ log verified" : "❌ log altered"}</li>
              {stats.synthetic_share > 0 ? (
                <li style={{ opacity: 0.85 }}>
                  Synthetic demo data ({formatShare(stats.synthetic_share)} of calls)
                </li>
              ) : null}
            </ul>
          ) : (
            <p style={{ margin: 0, opacity: 0.85 }}>No calls recorded yet.</p>
          )}
        </section>

        <p style={{ fontSize: "0.8rem", opacity: 0.75, marginTop: "auto" }}>{BEDSIDE_FOOTNOTE}</p>
        <p style={{ fontSize: "0.8rem", opacity: 0.75, margin: 0 }}>
          {connected ? "● live" : "○ connecting to the API…"}
          {thresholds.demo ? " · demo thresholds" : ""}
        </p>
      </aside>
    </div>
  );
}
