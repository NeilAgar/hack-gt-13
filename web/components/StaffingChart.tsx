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
}: {
  facilityName: string;
  curve: CurvePoint[];
  stateCurve: CurvePoint[];
}) {
  const facilityPoints = (curve ?? []).filter(
    (point) => Number.isFinite(point?.d) && Number.isFinite(point?.v),
  );
  if (facilityPoints.length === 0) {
    return <p>not enough inspections</p>;
  }

  const data = mergeCurves(facilityPoints, stateCurve ?? []);

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
          <YAxis tick={{ fill: "#5e584e", fontSize: 12 }} width={40} />
          <Tooltip
            formatter={(value, name) => {
              const numeric = typeof value === "number" ? value : Number(value);
              const shown = Number.isFinite(numeric) ? numeric.toFixed(2) : "—";
              return [shown, name];
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
          <Line
            type="monotone"
            dataKey="facility"
            name="This home"
            stroke="#a33b32"
            strokeWidth={2.4}
            dot={{ r: 3 }}
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
