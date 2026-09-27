import type { Metadata } from "next";

import { DEFAULT_CAPACITY, overdueCount } from "@/lib/regulator";
import { RiskPanel } from "@/components/RiskPanel";
import { SchedulePanel } from "@/components/SchedulePanel";
import { getFacilities, getTrophy, postSchedule } from "@/lib/api";
import { currentMonth, formatPct, formatRange, isScored } from "@/lib/format";
import type { ScheduleRequest, ScheduleResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

// Inspector/admin view: not linked from the site navigation, and kept out of search engines.
export const metadata: Metadata = {
  title: "Regulator demo · Pop Quiz",
  robots: { index: false, follow: false },
};

async function generateSchedule(body: ScheduleRequest): Promise<ScheduleResponse> {
  "use server";
  return postSchedule(body);
}

export default async function RegulatorPage() {
  const [trophy, facilities] = await Promise.all([getTrophy(), getFacilities("", 400)]);
  const byCcn = new Map(facilities.map((facility) => [facility.ccn, facility]));
  const names = Object.fromEntries(facilities.map((facility) => [facility.ccn, facility.name]));
  // The schedule marks every legally overdue home as forced; that count is the smallest usable capacity.
  let overdue = 0;
  try {
    overdue = overdueCount(await postSchedule({ month: currentMonth(), capacity: DEFAULT_CAPACITY, seed: 0 }));
  } catch {
    overdue = 0;
  }
  const minCapacity = Math.max(1, overdue);

  return (
    <>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        Regulator demo
      </p>
      <h1>Survey agency view</h1>
      <p className="lede">
        Trophy Check flags homes that meet a proxy for CMS&apos;s lighter Risk-Based Survey even
        when staffing is survey-responsive: it rises around inspections and falls afterward. Scores
        include the uncertainty range. PBJ staffing data is self-reported.
      </p>

      <section className="panel" aria-labelledby="trophy-heading">
        <h2 id="trophy-heading">Trophy Check</h2>
        {trophy.length === 0 ? (
          <p>No homes are flagged.</p>
        ) : (
          <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Home</th>
                <th>CCN</th>
                <th>Care Compare</th>
                <th>Score</th>
                <th>Uncertainty range</th>
              </tr>
            </thead>
            <tbody>
              {trophy.map((row) => {
                const match = byCcn.get(row.ccn);
                const range = match && isScored(match.score_pct, match.ci_low, match.ci_high)
                  ? formatRange(match.ci_low as number, match.ci_high as number)
                  : Number.isFinite(row.ci_low)
                    ? `lower bound ${formatPct(row.ci_low as number)}%`
                    : "—";
                return (
                  <tr key={row.ccn}>
                    <td className="wrap-name">{row.name}</td>
                    <td>{row.ccn}</td>
                    <td>{row.overall_star}★</td>
                    <td>{Number.isFinite(row.score_pct) ? `${formatPct(row.score_pct as number)}%` : "—"}</td>
                    <td>{range}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </section>

      <RiskPanel />
      <SchedulePanel generateSchedule={generateSchedule} minCapacity={minCapacity} overdue={overdue} names={names} />
    </>
  );
}
