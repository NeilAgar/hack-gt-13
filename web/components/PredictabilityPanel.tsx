import { formatProbability } from "@/lib/format";
import { topPredictability } from "@/lib/regulator";
import type { PredictabilityRow } from "@/lib/types";

export function PredictabilityPanel({ rows }: { rows: PredictabilityRow[] }) {
  const top = topPredictability(rows, 20);

  return (
    <section className="panel" aria-labelledby="predict-heading" style={{ marginTop: "1rem" }}>
      <h2 id="predict-heading">Predictability</h2>
      <p className="note">
        Internal only. This panel is never shown to families. It lists the 20 homes with the highest
        p_next_60d and does not give an inspection date.
      </p>
      {top.length === 0 ? (
        <p>No predictability scores are available.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Home</th>
                <th>CCN</th>
                <th>p_next_60d</th>
              </tr>
            </thead>
            <tbody>
              {top.map((row) => (
                <tr key={row.ccn}>
                  <td className="wrap-name">{row.name}</td>
                  <td>{row.ccn}</td>
                  <td>{formatProbability(row.p_next_60d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
