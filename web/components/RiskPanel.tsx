import { RISK_WEIGHTS as W, riskScore } from "@/lib/risk";

const TERMS = [
  {
    term: "Residents",
    weight: "multiplies everything",
    what: "Average residents per day (CMS Provider Information).",
    why: "Harm is counted in resident-months, so risk scales with how many people live there.",
  },
  {
    term: "Base",
    weight: `${W.base}`,
    what: "A floor for every home.",
    why: "A home with no warning signs still has some chance, so no home is ever safe for sure.",
  },
  {
    term: "S: staffing score",
    weight: `× ${W.score}`,
    what: "The home's rank among Georgia homes (0 = lowest, 1 = highest) on our survey-responsive staffing score: how much higher nurse hours per resident were around past inspections than a month later (PBJ + CMS inspection dates).",
    why: "This is what a randomized schedule exists to counter, so it gets a full weight.",
  },
  {
    term: "C: citations",
    weight: `× ${W.citations}`,
    what: `${W.harmPoints} per harm citation (severity G–I) plus ${W.ijPoints} per immediate-jeopardy citation (J–L), last 3 years, capped at 1 (CMS Health Deficiencies).`,
    why: "Actual harm, confirmed by inspectors and not self-reported, so it counts as much as our score. Immediate jeopardy counts double. The cap stops one extreme record from dominating.",
  },
  {
    term: "W: weekend dip",
    weight: `× ${W.weekend}`,
    what: "The home's rank (0–1) on how much lower nurse hours per resident are on weekends than weekdays (PBJ).",
    why: "A weaker, indirect sign: almost every home staffs less on weekends. It gets a small say.",
  },
];

const EXAMPLE = { residents: 100, harm: 0, ij: 0, weekendPercentile: 0.4 };
const typical = riskScore({ ...EXAMPLE, scorePercentile: 0.5 });
const responsive = riskScore({ ...EXAMPLE, scorePercentile: 0.9 });
const responsiveCited = riskScore({ ...EXAMPLE, scorePercentile: 0.9, ij: 1 });

export function RiskPanel() {
  return (
    <section className="panel" aria-labelledby="risk-heading" style={{ marginTop: "1rem" }}>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        How the schedule decides
      </p>
      <h2 id="risk-heading">Risk score</h2>
      <p className="meta">
        Each home gets one risk number. Higher risk means a higher chance of being picked this month.
      </p>
      <p className="equation">
        risk = residents × (0.25 + S + C + 0.25 × W)
      </p>

      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Term</th>
              <th>Weight</th>
              <th>What it measures</th>
              <th>Why this weight</th>
            </tr>
          </thead>
          <tbody>
            {TERMS.map((row) => (
              <tr key={row.term}>
                <td>{row.term}</td>
                <td style={{ whiteSpace: "nowrap" }}>{row.weight}</td>
                <td className="wrap-name">{row.what}</td>
                <td className="wrap-name">{row.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Example</h3>
      <p className="meta">
        Three homes with 100 residents and a weekend dip at the 40th percentile. The first has a
        middle-of-Georgia staffing score, the second a score higher than 90% of Georgia homes, and the
        third the same high score plus one immediate-jeopardy citation:
      </p>
      <p className="equation">
        100 × (0.25 + 0.5 + 0 + 0.25 × 0.4) = {Math.round(typical)}
        <br />
        100 × (0.25 + 0.9 + 0 + 0.25 × 0.4) = {Math.round(responsive)}
        <br />
        100 × (0.25 + 0.9 + 0.2 + 0.25 × 0.4) = {Math.round(responsiveCited)}
      </p>

      <h3>From risk to a schedule</h3>
      <ol className="meta">
        <li>Every home gets a risk number from the formula above.</li>
        <li>
          Homes more than 15.9 months past their last inspection are overdue by law and always get
          100%. Other homes whose last inspection fell in this same calendar month get 0%, so the next
          visit can&apos;t be guessed by adding a year to the last one.
        </li>
        <li>
          The remaining slots are shared out so that the riskiest homes get the highest chances. It
          keeps raising the top homes&apos; chances until no home is left with much more uncovered
          risk (risk × chance of <em>not</em> being picked) than any other.
        </li>
        <li>A random draw, weighted by those chances, picks the actual list.</li>
      </ol>

      <p className="note">
        The weights are judgement calls, not fitted to inspection outcomes. Ranks put every signal on
        the same 0–1 scale, so a weight says how much that signal counts. On Georgia data the staffing
        score is about half of the average multiplier and citations about a sixth, but citations reach
        the full 1 for the most-cited homes. Agency staffing share is not in our data yet, so it is not
        used. PBJ staffing data is self-reported.
      </p>
    </section>
  );
}
