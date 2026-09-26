"use client";

import { useState, type FormEvent } from "react";

import { currentMonth, formatProbability } from "@/lib/format";
import type { ScheduleRequest, ScheduleResponse } from "@/lib/types";

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
          <input
            type="number"
            min={1}
            step={1}
            value={capacity}
            onChange={(event) => setCapacity(Number(event.target.value))}
            required
          />
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
                  <td>{row.name}</td>
                  <td>{row.ccn}</td>
                  <td>{formatProbability(row.prob)}</td>
                  <td>{row.forced ? "Yes" : "No"}</td>
                  <td>{row.off_hours ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Probability each home is chosen</h3>
          <table>
            <thead>
              <tr>
                <th>CCN</th>
                <th>Probability</th>
                <th>Forced</th>
              </tr>
            </thead>
            <tbody>
              {result.probs.map((row) => (
                <tr key={row.ccn}>
                  <td>{row.ccn}</td>
                  <td>{formatProbability(row.prob)}</td>
                  <td>{row.forced ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
