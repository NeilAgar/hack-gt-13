"use client";

import { useState, type FormEvent } from "react";

import { currentMonth, formatProbability } from "@/lib/format";
import { clampCapacity, DEFAULT_CAPACITY, visibleProbabilities } from "@/lib/regulator";
import type { ScheduleRequest, ScheduleResponse } from "@/lib/types";

const CAPACITY_MAX = 40;

export function SchedulePanel({
  generateSchedule,
  minCapacity = 1,
  overdue = 0,
  names = {},
}: {
  generateSchedule: (body: ScheduleRequest) => Promise<ScheduleResponse>;
  /** Smallest capacity allowed: the number of legally overdue homes. */
  minCapacity?: number;
  overdue?: number;
  /** Home name by CCN, for the full probability table. */
  names?: Record<string, string>;
}) {
  const min = Math.min(Math.max(1, minCapacity), CAPACITY_MAX);
  const [month, setMonth] = useState(currentMonth);
  const [capacity, setCapacity] = useState(() => clampCapacity(DEFAULT_CAPACITY, min, CAPACITY_MAX));
  const set = (value: number) => setCapacity(clampCapacity(value, min, CAPACITY_MAX));
  const [result, setResult] = useState<ScheduleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [showAllProbs, setShowAllProbs] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const chosen = clampCapacity(capacity, min, CAPACITY_MAX);
      setCapacity(chosen);
      const schedule = await generateSchedule({ month, capacity: chosen });
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
              min={min}
              max={CAPACITY_MAX}
              step={1}
              value={capacity}
              aria-valuemin={min}
              aria-valuemax={CAPACITY_MAX}
              aria-valuenow={capacity}
              onChange={(event) => set(Number(event.target.value))}
            />
            <input
              type="number"
              min={min}
              max={CAPACITY_MAX}
              step={1}
              value={capacity}
              onChange={(event) => setCapacity(Number(event.target.value))}
              onBlur={() => set(capacity)}
              required
            />
          </span>
          {overdue > 0 ? (
            <span className="meta">
              Minimum {min}: {overdue} homes are legally overdue (more than 15.9 months since their last
              inspection) and must be inspected. Slots above {min} are the randomized picks.
            </span>
          ) : null}
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
                  <th>Home</th>
                  <th>CCN</th>
                  <th>Probability</th>
                  <th>Forced</th>
                </tr>
              </thead>
              <tbody>
                {visibleProbabilities(result.probs, showAllProbs).map((row) => (
                  <tr key={row.ccn}>
                    <td className="wrap-name">{names[row.ccn] ?? "—"}</td>
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
