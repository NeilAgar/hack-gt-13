import { RISK_WEIGHTS as W } from "@/lib/risk";

const TERMS = [
  { term: "Residents", weight: "×", why: "Average residents per day. More people affected if staffing is short." },
  { term: "Base", weight: `${W.base}`, why: "Every home keeps some chance of being picked." },
  {
    term: "S: staffing score",
    weight: `${W.score}`,
    why: "Rank (0–1) among Georgia homes on survey-responsive staffing. What random scheduling counters.",
  },
  {
    term: "C: citations",
    weight: `${W.citations}`,
    why: `${W.harmPoints} per harm + ${W.ijPoints} per immediate-jeopardy citation (3 years), capped at 1. Confirmed by inspectors.`,
  },
  {
    term: "W: weekend dip",
    weight: `${W.weekend}`,
    why: "Rank (0–1) on weekend staffing drop. A weaker sign, since most homes have one.",
  },
  {
    term: "T: time since last inspection",
    weight: `${W.time}`,
    why: "0 until 12 months, rising to 1 at the 15.9-month legal limit, so homes nearing it rank higher.",
  },
];

export function RiskPanel() {
  return (
    <section className="panel" aria-labelledby="risk-heading" style={{ marginTop: "1rem" }}>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        How the schedule decides
      </p>
      <h2 id="risk-heading">Risk Score</h2>
      <p className="meta">
        Each home gets one risk number. Higher risk means a higher chance of being picked this month.
      </p>
      <p className="equation">risk = residents × (0.25 + S + C + 0.25 × W + T)</p>

      <div style={{ overflowX: "auto" }}>
        <table className="compact-table">
          <thead>
            <tr>
              <th>Term</th>
              <th>Weight</th>
              <th>Meaning</th>
            </tr>
          </thead>
          <tbody>
            {TERMS.map((row) => (
              <tr key={row.term}>
                <td style={{ whiteSpace: "nowrap" }}>{row.term}</td>
                <td>{row.weight}</td>
                <td>{row.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="note">
        Weights are illustrative judgement calls, not fitted to inspection outcomes. PBJ staffing data is
        self-reported.
      </p>
    </section>
  );
}
