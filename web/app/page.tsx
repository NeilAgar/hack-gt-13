import { MapView } from "@/components/MapView";
import { getFacilities } from "@/lib/api";
import {
  isConsistencyLabel,
  LABEL_COLOR,
  LABEL_NOTE,
  LABEL_PENDING,
  NEUTRAL_COLOR,
  scoreSummary,
} from "@/lib/format";
import type { ConsistencyLabel } from "@/lib/types";

export const dynamic = "force-dynamic";

const LABELS: ConsistencyLabel[] = ["High", "Watch", "Low"];

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const facilities = await getFacilities(q, 400);

  return (
    <>
      <h1>Staffing consistency around state inspections</h1>
      <p className="lede">
        Search a Georgia nursing home or a city. Pins show Staffing Consistency: whether nurse
        hours per resident are higher in the 14 days through the day before past inspections ended
        than about a month later. A larger positive number means more survey-responsive staffing.
        Every score includes its uncertainty range. PBJ staffing data is self-reported.
      </p>
      <form className="search" action="/" method="get" role="search">
        <label className="sr-only" htmlFor="q">
          Search by city or nursing home
        </label>
        <input
          id="q"
          name="q"
          type="search"
          defaultValue={q}
          placeholder="Search a city or nursing home, such as Savannah"
          aria-label="Search by city or nursing home"
        />
        <button type="submit">Search</button>
      </form>
      <ul className="legend">
        {LABELS.map((label) => (
          <li key={label}>
            <span className="swatch" style={{ background: LABEL_COLOR[label] }} aria-hidden />
            <strong>{label}</strong>
            <span>{LABEL_NOTE[label]}</span>
          </li>
        ))}
        <li>
          <span className="swatch" style={{ background: NEUTRAL_COLOR }} aria-hidden />
          <strong>{LABEL_PENDING}</strong>
          <span>No score yet, or the High / Watch / Low cutoff is not set.</span>
        </li>
      </ul>
      <div className="explorer">
        <section aria-label="Search results">
          {facilities.length === 0 ? (
            <p className="panel">No homes match that search.</p>
          ) : (
            <ul className="facility-list">
              {facilities.map((facility) => {
                const label = isConsistencyLabel(facility.label) ? facility.label : null;
                return (
                <li key={facility.ccn} className="facility-card">
                  <h2>
                    <a href={`/facility/${facility.ccn}`}>{facility.name}</a>
                  </h2>
                  <p className="meta">
                    {facility.city} · Care Compare {facility.overall_star}★ · Staffing{" "}
                    {facility.staffing_star}★
                  </p>
                  <p>
                    <span className="chip">
                      <span
                        className="swatch"
                        style={{ background: label ? LABEL_COLOR[label] : NEUTRAL_COLOR }}
                        aria-hidden
                      />
                      {label ? `Staffing consistency: ${label}` : LABEL_PENDING}
                    </span>
                  </p>
                  <p className="score">
                    {scoreSummary(facility.score_pct, facility.ci_low, facility.ci_high)}
                  </p>
                </li>
                );
              })}
            </ul>
          )}
        </section>
        <MapView facilities={facilities} />
      </div>
    </>
  );
}
