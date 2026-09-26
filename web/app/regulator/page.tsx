import { PredictabilityPanel } from "@/components/PredictabilityPanel";
import { SchedulePanel } from "@/components/SchedulePanel";
import { SimulationChart } from "@/components/SimulationChart";
import { getFacilities, getPredictability, getSimulate, getTrophy, postSchedule } from "@/lib/api";
import { formatPct, formatRange, isScored } from "@/lib/format";
import type { ScheduleRequest, ScheduleResponse, SimulateResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

async function generateSchedule(body: ScheduleRequest): Promise<ScheduleResponse> {
  "use server";
  return postSchedule(body);
}

async function loadSimulation(capacity: number): Promise<SimulateResponse> {
  "use server";
  return getSimulate(capacity);
}

export default async function RegulatorPage() {
  const [trophy, facilities, simulation, predictability] = await Promise.all([
    getTrophy(),
    getFacilities("", 400),
    getSimulate(3),
    getPredictability(),
  ]);
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

      <SchedulePanel generateSchedule={generateSchedule} />
      <SimulationChart initialSimulation={simulation} loadSimulation={loadSimulation} />
      <PredictabilityPanel rows={predictability} />
    </>
  );
}
