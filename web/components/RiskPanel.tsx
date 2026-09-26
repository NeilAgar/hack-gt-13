import { RISK_WEIGHTS as W, riskScore } from "@/lib/risk";

const TERMS = [
  {
    term: "Residents",
    weight: "multiplies everything",
    what: "Average residents per day. More residents means more people affected if staffing is short.",
    source: "CMS Provider Information",
  },
  {
    term: "Base",
    weight: `${W.base}`,
    what: "A floor so every home keeps some risk, even with no warning signs.",
    source: "Fixed",
  },
  {
    term: "Score",
    weight: `÷ ${W.scoreDivisor}`,
    what: "Our survey-responsive staffing score: how much higher nurse hours per resident were around past inspections than a month later, in %. Negative scores count as 0.",
    source: "PBJ + CMS inspection dates (our analysis)",
  },
  {
    term: "Harm citations",
    weight: `× ${W.harm}`,
    what: "Citations where residents were actually harmed (severity G–I), last 3 years.",
    source: "CMS Health Deficiencies",
  },
  {
    term: "Immediate jeopardy",
    weight: `× ${W.ij}`,
    what: "The most serious citations (severity J–L), last 3 years. Weighted twice as much as harm.",
    source: "CMS Health Deficiencies",
  },
  {
    term: "Weekend dip",
    weight: `÷ ${W.weekendDivisor}`,
    what: "How much lower nurse hours per resident are on weekends than on weekdays, in %.",
    source: "PBJ",
  },
  {
    term: "Agency share",
    weight: `× ${W.agency}`,
    what: "Share of hours worked by agency (temporary) staff. Not in our data yet, so it is 0 for every home.",
    source: "Not loaded",
  },
];

const EXAMPLE = { residents: 100, harm: 0, ij: 0, weekendDipPct: 18 };
const steady = riskScore({ ...EXAMPLE, scorePct: 1 });
const responsive = riskScore({ ...EXAMPLE, scorePct: 10 });

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
        risk = residents × (0.25 + score ÷ 10 + 0.2 × harm + 0.4 × IJ + weekend dip ÷ 20 + 2 × agency share)
      </p>

      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Term</th>
              <th>Weight</th>
              <th>What it measures</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {TERMS.map((row) => (
              <tr key={row.term}>
                <td>{row.term}</td>
                <td style={{ whiteSpace: "nowrap" }}>{row.weight}</td>
                <td className="wrap-name">{row.what}</td>
                <td>{row.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Example</h3>
      <p className="meta">
        Two homes with 100 residents, no harm or immediate-jeopardy citations and an 18% weekend dip.
        One has a score of 1%, the other 10%:
      </p>
      <p className="equation">
        100 × (0.25 + 1 ÷ 10 + 18 ÷ 20) = {Math.round(steady)}
        <br />
        100 × (0.25 + 10 ÷ 10 + 18 ÷ 20) = {Math.round(responsive)}
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
        The weights are illustrative. They were set by hand, not fitted to inspection outcomes. On
        Georgia data the weekend dip is the largest part of the multiplier for most homes (about half
        on average), because almost every home staffs about 18% less on weekends. PBJ staffing data is
        self-reported.
      </p>
    </section>
  );
}
