"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { mergeCurves } from "@/lib/format";
import type { CurvePoint } from "@/lib/types";

export function StaffingChart({
  facilityName,
  curve,
  stateCurve,
  normalP95 = null,
  xDomain = [-42, 56],
  showState = true,
  height = 400,
}: {
  facilityName: string;
  curve: CurvePoint[];
  stateCurve: CurvePoint[];
  /** This home's normal-day line (95th percentile of its ordinary days); null draws no line. */
  normalP95?: number | null;
  /** Days shown, relative to the inspection end (day 0). */
  xDomain?: [number, number];
  /** Draw the Georgia average line. */
  showState?: boolean;
  height?: number;
}) {
  const [x0, x1] = xDomain;
  const span = x1 - x0;
  const step = span <= 16 ? 1 : span <= 30 ? 2 : 14;
  const ticks: number[] = [];
  for (let d = Math.ceil(x0 / step) * step; d <= x1; d += step) ticks.push(d);
  const facilityPoints = (curve ?? []).filter(
    (point) => Number.isFinite(point?.d) && Number.isFinite(point?.v) && point.d >= x0 && point.d <= x1,
  );
  if (facilityPoints.length === 0) {
    return <p>not enough inspections</p>;
  }

  const data = mergeCurves(
    facilityPoints,
    showState ? (stateCurve ?? []).filter((point) => point.d >= x0 && point.d <= x1) : [],
  );
  const line = typeof normalP95 === "number" && Number.isFinite(normalP95) ? normalP95 : null;
  const isAbove = (v: unknown) => line !== null && typeof v === "number" && v > line;

  return (
    <div className="chart-wrap" style={{ height }} aria-label={`Staffing curve for ${facilityName}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 18, right: 16, left: 12, bottom: 18 }}>
          <CartesianGrid stroke="#e3d7c6" />
          <XAxis
            dataKey="d"
            type="number"
            domain={[x0, x1]}
            ticks={ticks}
            allowDataOverflow
            tick={{ fill: "#5e584e", fontSize: 12 }}
            height={44}
            label={{ value: "Days from inspection end (day 0)", position: "insideBottom", offset: -4, fill: "#5e584e", fontSize: 12 }}
          />
          <YAxis
            tick={{ fill: "#5e584e", fontSize: 12 }}
            width={56}
            label={{
              value: "Hours per resident vs usual",
              angle: -90,
              position: "insideLeft",
              offset: 8,
              style: { textAnchor: "middle", fill: "#5e584e", fontSize: 12 },
            }}
            domain={[
              (dataMin: number) => Math.min(dataMin, 0),
              // Headroom above the highest point (or the normal-day line) so peaks aren't clipped.
              (dataMax: number) => Math.max(dataMax, line ?? dataMax) * 1.15,
            ]}
            tickFormatter={(v: number) => (Math.abs(v) < 0.05 ? 0 : v).toFixed(1)}
          />
          <Tooltip
            formatter={(value, name) => {
              const numeric = typeof value === "number" ? value : Number(value);
              const shown = Number.isFinite(numeric) ? numeric.toFixed(2) : "—";
              const note = name === "This home" && isAbove(numeric) ? " (above this home's normal range)" : "";
              return [shown + note, name];
            }}
            labelFormatter={(label) => `Day ${label}`}
          />
          <Legend
            verticalAlign="top"
            height={28}
            payload={[
              { value: "This home", type: "line", id: "facility", color: "#a33b32" },
              ...(line !== null
                ? [{ value: "This home's normal (95% of ordinary days)", type: "plainline" as const, id: "normal", color: "#6b5b95", payload: { strokeDasharray: "2 4" } }]
                : []),
              ...(showState
                ? [{ value: "Georgia average", type: "plainline" as const, id: "state", color: "#5e584e", payload: { strokeDasharray: "5 4" } }]
                : []),
            ]}
          />
          <ReferenceLine x={0} stroke="#123f4c" strokeWidth={2} />
          {line !== null && (
            <ReferenceLine
              y={line}
              stroke="#6b5b95"
              strokeWidth={1.6}
              strokeDasharray="2 4"
              ifOverflow="extendDomain"
            />
          )}
          <Line
            type="monotone"
            dataKey="facility"
            name="This home"
            stroke="#a33b32"
            strokeWidth={2.4}
            dot={(props: { cx?: number; cy?: number; index?: number; payload?: { facility?: number | null } }) => {
              const { cx, cy, index, payload } = props;
              if (cx == null || cy == null || payload?.facility == null) return <g key={`d-${index}`} />;
              return isAbove(payload.facility) ? (
                <circle key={`d-${index}`} cx={cx} cy={cy} r={5} fill="#a33b32" stroke="#fffdf8" strokeWidth={2} />
              ) : (
                <circle key={`d-${index}`} cx={cx} cy={cy} r={2.5} fill="#a33b32" />
              );
            }}
            connectNulls
          />
          {showState && (
            <Line
              type="monotone"
              dataKey="state"
              name="Georgia average"
              stroke="#5e584e"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
