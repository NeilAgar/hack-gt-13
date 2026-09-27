import { MapView } from "@/components/MapView";
import { getFacilities } from "@/lib/api";
import {
  formatRange,
  formatSignedPct,
  isConsistencyLabel,
  isScored,
  LABEL_COLOR,
  LABEL_PENDING,
  NEUTRAL_COLOR,
  staffTraceRating,
  RATING_COLOR,
  UNRATED_COLOR,
  scoreSummary,
  starString,
} from "@/lib/format";

export const dynamic = "force-dynamic";

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
        Search a Georgia nursing home or a city. On the map, each dot&apos;s color is the home&apos;s StaffTrace
        rating. Open a home to see its staffing consistency: whether nurse hours per resident are higher
        in the 14 days through the day before past inspections ended than about a month later, a sign of
        survey-responsive staffing. Every score includes its uncertainty range. PBJ staffing data is
        self-reported.
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
      <div className="map-legend" aria-label="Map legend">
        <div>
          <p className="legend-title">Dot color: StaffTrace rating</p>
          <ul className="legend">
            {([1, 2, 3, 4, 5] as const).map((stars) => (
              <li key={stars}>
                <span className="swatch" style={{ background: RATING_COLOR[stars] }} aria-hidden />
                <strong>{stars}★</strong>
              </li>
            ))}
            <li>
              <span className="swatch" style={{ background: UNRATED_COLOR }} aria-hidden />
              <span>Not rated by CMS</span>
            </li>
          </ul>
        </div>
      </div>
      <div className="explorer">
        <section aria-label="Search results">
          {facilities.length === 0 ? (
            <p className="panel">No homes match that search.</p>
          ) : (
            <ul className="facility-list">
              {facilities.map((facility) => {
                const label = isConsistencyLabel(facility.label) ? facility.label : null;
                const rating = staffTraceRating(facility.overall_star, facility.adjusted_star);
                return (
                <li key={facility.ccn}>
                  <details className="facility-item">
                    <summary className="facility-toggle">{facility.name}</summary>
                    <div className="facility-card">
                      <p className="meta">{facility.city}</p>
                      {rating.staffTrace !== null ? (
                        <p className="tile-rating" aria-label={`StaffTrace rating ${rating.staffTrace} out of 5 stars`}>
                          <span className="tile-stars" aria-hidden>{starString(rating.staffTrace)}</span>{" "}
                          <strong>StaffTrace {rating.staffTrace}★</strong>
                          {rating.lowered ? (
                            <span className="lowered-badge small"> ↓ lowered from CMS {rating.cms}★</span>
                          ) : (
                            <span className="meta"> · same as CMS</span>
                          )}
                        </p>
                      ) : (
                        <p className="meta">Not rated by CMS</p>
                      )}
                      <p className="meta">
                        CMS Care Compare {facility.overall_star}★ overall · {facility.staffing_star}★ staffing
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
                        {isScored(facility.score_pct, facility.ci_low, facility.ci_high)
                          ? `Staffing change around inspections: ${formatSignedPct(facility.score_pct as number)} (range ${formatRange(facility.ci_low as number, facility.ci_high as number)})`
                          : scoreSummary(facility.score_pct, facility.ci_low, facility.ci_high)}
                      </p>
                      <a className="tile-link" href={`/facility/${facility.ccn}`}>
                        See full details →
                      </a>
                    </div>
                  </details>
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
