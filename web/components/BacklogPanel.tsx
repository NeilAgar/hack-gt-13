"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { homesInBucket, nextMonthOverdue, summarizeBacklog } from "@/lib/backlog";
import type { BacklogResponse, ScheduleResponse } from "@/lib/types";

const AXIS_TICK = { fill: "#5e584e", fontSize: 12 };
const GRID = "#e3d7c6";

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/**
 * Inspection backlog: how long each Georgia home has gone since its last standard inspection, and its
 * chance of being picked under the current plan. Regulator only; uses past inspection dates.
 */
export function BacklogPanel({
  backlog,
  schedule,
  names,
}: {
  backlog: BacklogResponse;
  schedule: ScheduleResponse;
  names: Record<string, string>;
}) {
  const homes = backlog.homes;
  if (homes.length === 0) return null;

  const buckets = summarizeBacklog(homes, schedule.probs);
  const next = nextMonthOverdue(homes, schedule.probs, backlog.forced_weeks);
  const overdueNow = homes.filter((home) => home.forced).length;
  const picked = schedule.selected.map((row) => row.ccn);

  return (
    <section className="panel backlog" aria-labelledby="backlog-heading" style={{ marginTop: "1rem" }}>
      <h2 id="backlog-heading">Inspection Backlog</h2>
      <p className="meta">
        Months since each home&apos;s last standard inspection, as of {backlog.as_of}, and its chance of being
        picked in the {schedule.month} plan ({schedule.capacity} inspections). Federal rules allow at most 15.9
        months between standard inspections.
      </p>

      <div className="stat-row">
        <div className="stat">
          <b>{overdueNow}</b>
          <span>overdue now (always picked)</span>
        </div>
        <div className="stat">
          <b>{next.crossing}</b>
          <span>cross 15.9 months within a month</span>
        </div>
        <div className="stat">
          <b>≈ {Math.round(next.expectedOverdue)}</b>
          <span>of those expected to be overdue next month at this capacity</span>
        </div>
      </div>

      <div className="backlog-charts">
        <figure className="backlog-figure">
          <figcaption>Homes by time since last inspection</figcaption>
          <div className="chart-wrap" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 20, right: 8, left: 0, bottom: 4 }} barCategoryGap="22%">
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="label" tick={AXIS_TICK} interval={0} />
                <YAxis tick={AXIS_TICK} width={36} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(0,0,0,0.04)" }}
                  formatter={(value, _name, item) => {
                    const row = item?.payload as (typeof buckets)[number] | undefined;
                    return [
                      `${value} homes · avg chance ${row ? pct(row.avgChance) : "—"} · ≈ ${row ? row.expectedPicks.toFixed(1) : "—"} inspections`,
                      "",
                    ];
                  }}
                  separator=""
                />
                <Bar dataKey="homes" name="Homes" radius={[4, 4, 0, 0]}>
                  {buckets.map((bucket) => (
                    <Cell key={bucket.id} fill={bucket.color} />
                  ))}
                  <LabelList dataKey="homes" position="top" fill="#1b242c" fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </figure>
      </div>

      <div className="table-scroll">
        <table className="compact-table">
          <thead>
            <tr>
              <th>Since last inspection</th>
              <th>Homes</th>
              <th>Average chance this month</th>
              <th>Expected inspections</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket) => (
              <tr key={bucket.id}>
                <td>
                  <span className="swatch" style={{ background: bucket.color }} aria-hidden /> {bucket.label}
                </td>
                <td>{bucket.homes}</td>
                <td>{pct(bucket.avgChance)}</td>
                <td>{bucket.expectedPicks.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3 className="backlog-lists-title">Homes in each group</h3>
      {buckets.map((bucket) => {
        const rows = homesInBucket(homes, schedule.probs, picked, bucket.id);
        const onList = rows.filter((row) => row.picked).length;
        return (
          <details key={bucket.id} className="backlog-group">
            <summary>
              <span className="swatch" style={{ background: bucket.color }} aria-hidden />
              <strong>{bucket.label}</strong>
              <span className="meta">
                {bucket.homes} homes · {onList} on this month&apos;s list
              </span>
            </summary>
            {rows.length === 0 ? (
              <p className="meta">No homes in this group.</p>
            ) : (
              <div className="table-scroll">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>Home</th>
                      <th>CCN</th>
                      <th>Months since last inspection</th>
                      <th>Chance this month</th>
                      <th>On this month&apos;s list</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.ccn}>
                        <td className="wrap-name">
                          <a href={`/facility/${row.ccn}`}>{names[row.ccn] ?? row.ccn}</a>
                        </td>
                        <td>{row.ccn}</td>
                        <td>{row.months.toFixed(1)}</td>
                        <td>{pct(row.chance)}</td>
                        <td>{row.picked ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
        );
      })}

      <p className="note">
        Expected inspections add up each home&apos;s chance, so they sum to the plan&apos;s capacity. Past inspection
        dates only; this view is never shown to families.
      </p>
    </section>
  );
}
