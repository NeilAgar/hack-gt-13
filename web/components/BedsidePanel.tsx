"use client";

import { useEffect, useState } from "react";

/**
 * "Measured at the bedside": Call Clock stats for one facility.
 * Mount on the facility page: <BedsidePanel ccn={ccn} />
 * Data: GET {NEXT_PUBLIC_API_BASE}/facility/{ccn}/bedside (contract v1.1 "Bedside").
 * Wording rule: "time until someone arrived", never "time to help".
 */

export type BedsideEvent = {
  device_id: string;
  seq: number;
  ccn: string;
  call_id: string;
  event: "call_on" | "entry" | "cancel" | "timeout";
  ts: string | null;
  wait_s: number | null;
  no_entry: boolean | null;
  night: boolean | null;
  synthetic: boolean;
  verified: boolean;
  reason: string | null;
  received_at_ms: number;
};

export type BedsideStats = {
  ccn: string;
  n_devices: number;
  n_calls: number;
  median_wait_s: number | null;
  p_over_10m: number | null;
  night_median_wait_s: number | null;
  day_median_wait_s: number | null;
  n_no_entry: number;
  verified_all: boolean;
  n_unverified?: number;
  synthetic_share: number;
  recent: BedsideEvent[];
  by_days_since_inspection: { bucket: string; median_wait_s: number | null; n: number }[] | null;
};

export const BEDSIDE_FOOTNOTE =
  "Independent, camera-free device. Time until someone arrived, not time to care. One room is evidence, not a verdict.";

export function bedsideApiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api").replace(/\/$/, "");
}

/** 21.4 → "0:21"; 671 → "11:11". */
export function formatWait(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "–";
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function describeEvent(ev: BedsideEvent): string {
  switch (ev.event) {
    case "call_on":
      return "Call light on";
    case "entry":
      return `Someone arrived after ${formatWait(ev.wait_s)}`;
    case "cancel":
      return ev.no_entry ? "Cancelled with no one entering" : "Call light off";
    case "timeout":
      return ev.no_entry ? "Stopped timing after 2 h, no one entered" : "Stopped timing after 2 h";
  }
}

/** Share of calls that are synthetic, never rounded up to 100% or down to 0%. */
export function formatShare(share: number): string {
  if (share >= 1) return "100%";
  if (share > 0.99) return ">99%";
  if (share > 0 && share < 0.01) return "<1%";
  return `${Math.round(share * 100)}%`;
}

function formatTime(ts: string | null): string {
  if (!ts) return "time not set";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  });
}

export function BedsidePanel({
  ccn,
  includeSynthetic = true,
  refreshMs = 15000,
}: {
  ccn: string;
  includeSynthetic?: boolean;
  refreshMs?: number;
}) {
  const [stats, setStats] = useState<BedsideStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const url = `${bedsideApiBase()}/facility/${encodeURIComponent(ccn)}/bedside?include_synthetic=${includeSynthetic}`;
    async function load() {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`API responded ${res.status}`);
        const body = (await res.json()) as BedsideStats;
        if (!cancelled) {
          setStats(body);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "request failed");
      }
    }
    void load();
    const timer = refreshMs > 0 ? setInterval(load, refreshMs) : undefined;
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [ccn, includeSynthetic, refreshMs]);

  return (
    <section className="panel" aria-labelledby="bedside-heading" style={{ marginTop: "1rem" }}>
      <h2 id="bedside-heading">Measured at the bedside</h2>

      {error && !stats ? (
        <p className="meta">Bedside measurements are unavailable right now ({error}).</p>
      ) : !stats ? (
        <p className="meta">Loading bedside measurements…</p>
      ) : stats.n_calls === 0 && stats.recent.length === 0 ? (
        <p className="meta">No Call Clock device has reported from this home yet.</p>
      ) : (
        <BedsideBody stats={stats} />
      )}

      <p className="note" style={{ marginTop: "0.75rem" }}>
        {BEDSIDE_FOOTNOTE}
      </p>
    </section>
  );
}

function BedsideBody({ stats }: { stats: BedsideStats }) {
  const pctOver =
    stats.p_over_10m === null ? "–" : `${Math.round(stats.p_over_10m * 100)}%`;
  const nUnverified = stats.n_unverified ?? 0;

  return (
    <>
      <p style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
        {stats.verified_all ? (
          <span className="chip" title="Every event's hash chain and device signature checked out">
            ✅ log verified
          </span>
        ) : (
          <span
            className="chip"
            style={{ borderColor: "#a23b2a", color: "#a23b2a" }}
            title="At least one event failed hash-chain or signature checks; failed events are left out of the numbers"
          >
            ❌ log altered{nUnverified ? ` (${nUnverified} event${nUnverified === 1 ? "" : "s"} failed checks)` : ""}
          </span>
        )}
        {stats.synthetic_share > 0 ? (
          <span className="chip" style={{ background: "#fff3d6" }}>
            Synthetic demo data ({formatShare(stats.synthetic_share)} of calls)
          </span>
        ) : null}
      </p>
      <p className="meta">
        Based on {stats.n_calls} call{stats.n_calls === 1 ? "" : "s"} from {stats.n_devices} device
        {stats.n_devices === 1 ? "" : "s"}. The device watches the call light and the doorway; it has no
        camera and no microphone.
      </p>

      <div className="stat-row">
        <div className="stat">
          <b>{formatWait(stats.median_wait_s)}</b>
          <span>Median time until someone arrived</span>
        </div>
        <div className="stat">
          <b>{pctOver}</b>
          <span>Waits over 10 minutes</span>
        </div>
        <div className="stat">
          <b>
            {formatWait(stats.night_median_wait_s)} / {formatWait(stats.day_median_wait_s)}
          </b>
          <span>Median at night (11 pm–7 am) / by day</span>
        </div>
        <div className="stat">
          <b>{stats.n_no_entry}</b>
          <span>Calls cancelled with no one entering</span>
        </div>
      </div>

      {stats.by_days_since_inspection ? (
        <>
          <h3 style={{ fontSize: "1rem", marginBottom: "0.25rem" }}>By days since the last inspection</h3>
          <table style={{ borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", paddingRight: "1rem" }}>Days since</th>
                <th style={{ textAlign: "left", paddingRight: "1rem" }}>Median wait</th>
                <th style={{ textAlign: "left" }}>Calls</th>
              </tr>
            </thead>
            <tbody>
              {stats.by_days_since_inspection.map((row) => (
                <tr key={row.bucket}>
                  <td style={{ paddingRight: "1rem" }}>{row.bucket}</td>
                  <td style={{ paddingRight: "1rem" }}>{formatWait(row.median_wait_s)}</td>
                  <td>{row.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {stats.recent.length ? (
        <>
          <h3 style={{ fontSize: "1rem", marginBottom: "0.25rem" }}>Recent events</h3>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "0.9rem" }}>
            {stats.recent.slice(0, 8).map((ev) => (
              <li
                key={`${ev.device_id}-${ev.seq}`}
                style={{ padding: "0.2rem 0", borderBottom: "1px solid var(--line)" }}
              >
                <span className="meta" style={{ display: "inline-block", minWidth: "9.5rem" }}>
                  {formatTime(ev.ts)}
                </span>
                {describeEvent(ev)}
                {ev.synthetic ? <span className="meta"> · synthetic</span> : null}
                {ev.verified ? null : (
                  <span style={{ color: "#a23b2a" }} title={ev.reason ?? undefined}>
                    {" "}
                    · ❌ failed checks
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

export default BedsidePanel;
