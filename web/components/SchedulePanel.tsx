"use client";

import { useState, type FormEvent } from "react";

import { currentMonth, formatProbability } from "@/lib/format";
import { visibleProbabilities } from "@/lib/regulator";
import type { ScheduleRequest, ScheduleResponse } from "@/lib/types";

const CAPACITY_MAX = 40;

export function SchedulePanel({
  generateSchedule,
}: {
  generateSchedule: (body: ScheduleRequest) => Promise<ScheduleResponse>;
}) {
  const [month, setMonth] = useState(currentMonth);
  const [capacity, setCapacity] = useState(3);
  const [result, setResult] = useState<ScheduleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [showAllProbs, setShowAllProbs] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const schedule = await generateSchedule({ month, capacity });
      setResult(schedule);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Could not generate a schedule.";
      setError(message);
      setResult(null);
    } finally {
      setPending(false);
    }
  }

  return (
    <>
    <section className="panel" aria-labelledby="schedule-heading" style={{ marginTop: "1rem" }}>
      <h2 id="schedule-heading">Inspection schedule</h2>
      <p className="meta">
        Set inspector capacity, then generate this month&apos;s randomized list. The probability is
        the chance a home is chosen under that capacity.
      </p>
      <form className="schedule-form" onSubmit={onSubmit}>
        <label>
          Month
          <input
            type="month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            required
          />
        </label>
        <label>
          Inspector capacity
          <span className="capacity-control">
            <input
              type="range"
              min={1}
              max={CAPACITY_MAX}
              step={1}
              value={Number.isInteger(capacity) ? capacity : 1}
              aria-valuemin={1}
              aria-valuemax={CAPACITY_MAX}
              aria-valuenow={Number.isInteger(capacity) ? capacity : 1}
              onChange={(event) => setCapacity(Number(event.target.value))}
            />
            <input
              type="number"
              min={1}
              max={CAPACITY_MAX}
              step={1}
              value={capacity}
              onChange={(event) => setCapacity(Number(event.target.value))}
              required
            />
          </span>
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "Generating…" : "Generate"}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div aria-live="polite">
          <h3>
            Selected for {result.month} ({result.selected.length} of capacity {result.capacity})
          </h3>
          <table>
            <thead>
              <tr>
                <th>Home</th>
                <th>CCN</th>
                <th>Probability</th>
                <th>Forced</th>
                <th>Off-hours</th>
              </tr>
            </thead>
            <tbody>
              {result.selected.map((row) => (
                <tr key={row.ccn}>
                  <td className="wrap-name">{row.name}</td>
                  <td>{row.ccn}</td>
                  <td>{formatProbability(row.prob)}</td>
                  <td>{row.forced ? "Yes" : "No"}</td>
                  <td>{row.off_hours ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Probability each home is chosen</h3>
          <button type="button" onClick={() => setShowAllProbs((current) => !current)}>
            {showAllProbs ? "Show only homes above 0%" : "Show all"}
          </button>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>CCN</th>
                  <th>Probability</th>
                  <th>Forced</th>
                </tr>
              </thead>
              <tbody>
                {visibleProbabilities(result.probs, showAllProbs).map((row) => (
                  <tr key={row.ccn}>
                    <td>{row.ccn}</td>
                    <td>{formatProbability(row.prob)}</td>
                    <td>{row.forced ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
    </>
  );
}
