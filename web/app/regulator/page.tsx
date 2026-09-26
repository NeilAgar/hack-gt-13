import { SchedulePanel } from "@/components/SchedulePanel";
import { getFacilities, getTrophy, postSchedule } from "@/lib/api";
import { formatPct, formatRange } from "@/lib/format";
import type { ScheduleRequest, ScheduleResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

async function generateSchedule(body: ScheduleRequest): Promise<ScheduleResponse> {
  "use server";
  return postSchedule(body);
}

export default async function RegulatorPage() {
  const [trophy, facilities] = await Promise.all([getTrophy(), getFacilities("", 500)]);
  const byCcn = new Map(facilities.map((facility) => [facility.ccn, facility]));

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
                const range = match
                  ? formatRange(match.ci_low, match.ci_high)
                  : `lower bound ${formatPct(row.ci_low)}%`;
                return (
                  <tr key={row.ccn}>
                    <td>{row.name}</td>
                    <td>{row.ccn}</td>
                    <td>{row.overall_star}★</td>
                    <td>{formatPct(row.score_pct)}%</td>
                    <td>{range}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <SchedulePanel generateSchedule={generateSchedule} />
    </>
  );
}
