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
}: {
  facilityName: string;
  curve: CurvePoint[];
  stateCurve: CurvePoint[];
  /** This home's normal-day line (95th percentile of its ordinary days); null draws no line. */
  normalP95?: number | null;
}) {
  const facilityPoints = (curve ?? []).filter(
    (point) => Number.isFinite(point?.d) && Number.isFinite(point?.v),
  );
  if (facilityPoints.length === 0) {
    return <p>not enough inspections</p>;
  }

  const data = mergeCurves(facilityPoints, stateCurve ?? []);
  const line = typeof normalP95 === "number" && Number.isFinite(normalP95) ? normalP95 : null;
  const isAbove = (v: unknown) => line !== null && typeof v === "number" && v > line;

  return (
    <div className="chart-wrap" aria-label={`Staffing curve for ${facilityName}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 18, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#e3d7c6" />
          <XAxis
            dataKey="d"
            type="number"
            domain={[-42, 56]}
            ticks={[-42, -28, -14, 0, 14, 28, 42, 56]}
            tick={{ fill: "#5e584e", fontSize: 12 }}
            height={32}
          />
          <YAxis
            tick={{ fill: "#5e584e", fontSize: 12 }}
            width={40}
            domain={[
              (dataMin: number) => Math.min(dataMin, 0),
              // Headroom above the highest point (or the normal-day line) so peaks aren't clipped.
              (dataMax: number) => Math.max(dataMax, line ?? dataMax) * 1.15,
            ]}
            tickFormatter={(v: number) => v.toFixed(1)}
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
          <Legend verticalAlign="bottom" />
          <ReferenceLine
            x={0}
            stroke="#123f4c"
            strokeWidth={2}
            label={{ value: "Day 0", position: "insideTop", fill: "#123f4c", fontSize: 12 }}
          />
          {line !== null && (
            <ReferenceLine
              y={line}
              stroke="#6b5b95"
              strokeWidth={1.6}
              strokeDasharray="2 4"
              ifOverflow="extendDomain"
              label={{ value: "This home's normal (95%)", position: "insideTopRight", fill: "#6b5b95", fontSize: 12 }}
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
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
