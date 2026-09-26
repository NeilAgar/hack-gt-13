"use client";

import { useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCount, formatPct, reductionCaption } from "@/lib/format";
import type { SimulateResponse } from "@/lib/types";

const BAR_COLORS = ["#8d7b66", "#123f4c"];

export function SimulationChart({
  initialSimulation,
  loadSimulation,
}: {
  initialSimulation: SimulateResponse;
  loadSimulation: (capacity: number) => Promise<SimulateResponse>;
}) {
  const [capacity, setCapacity] = useState(3);
  const [simulation, setSimulation] = useState(initialSimulation);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run(nextCapacity: number) {
    if (!Number.isInteger(nextCapacity) || nextCapacity < 1) {
      setError("Capacity must be a positive integer.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      setSimulation(await loadSimulation(nextCapacity));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not run the simulation.");
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(capacity);
  }

  const statusQuo = simulation.status_quo?.undetected_shirk_resident_months;
  const popQuiz = simulation.popquiz?.undetected_shirk_resident_months;
  const ready = Number.isFinite(statusQuo) && Number.isFinite(popQuiz);
  const caption = reductionCaption(simulation.reduction_pct);
  const data = ready
    ? [
        { schedule: "Status quo", value: statusQuo },
        { schedule: "Pop Quiz", value: popQuiz },
      ]
    : [];

  return (
    <section className="panel" aria-labelledby="sim-heading" style={{ marginTop: "1rem" }}>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        Illustrative model
      </p>
      <h2 id="sim-heading">Simulation</h2>
      <p className="meta">
        Status quo versus the Pop Quiz schedule, at the same inspector budget. The bars are
        undetected shirk resident-months over {simulation.months} months. This is not an estimate of
        lives saved. {"Chen & Dillender (NBER w34037) and Gandhi, Olenski & Shi (NBER w34491)."}
      </p>
      <form className="schedule-form" onSubmit={onSubmit}>
        <label>
          Capacity
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
          {pending ? "Running…" : "Run"}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {ready ? (
        <>
          <div className="stat-row">
            <div className="stat">
              <b>{formatCount(statusQuo)}</b>
              <span>Status quo</span>
            </div>
            <div className="stat">
              <b>{formatCount(popQuiz)}</b>
              <span>Pop Quiz</span>
            </div>
            <div className="stat">
              <b>{Number.isFinite(simulation.reduction_pct) ? `${formatPct(simulation.reduction_pct)}%` : "—"}</b>
              <span>Reduction</span>
            </div>
          </div>
          {caption ? <p className="note">{caption}</p> : null}
          <div className="chart-wrap chart-short">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="#e3d7c6" vertical={false} />
                <XAxis dataKey="schedule" tick={{ fill: "#5e584e", fontSize: 13 }} />
                <YAxis
                  width={72}
                  tick={{ fill: "#5e584e", fontSize: 12 }}
                  tickFormatter={(value: number) => formatCount(value)}
                />
                <Tooltip
                  formatter={(value) => [
                    formatCount(Number(value)),
                    "undetected shirk resident-months",
                  ]}
                />
                <Bar dataKey="value" name="undetected shirk resident-months" radius={[6, 6, 0, 0]}>
                  {data.map((row, index) => (
                    <Cell key={row.schedule} fill={BAR_COLORS[index]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <p>The simulation is not available for this capacity.</p>
      )}
    </section>
  );
}
