import {
  formatRange,
  formatSignedPct,
  isScored,
  LABEL_COLOR,
  LABEL_NOTE,
  LABEL_PENDING,
  NEUTRAL_COLOR,
  popQuizRating,
  scoreHeadline,
  starString,
  UNSCORED_COPY,
} from "@/lib/format";
import type { ConsistencyLabel } from "@/lib/types";

/**
 * The top of the facility page: the Pop Quiz rating first and largest, a clear badge when it
 * is lower than CMS's, the percentage change around inspections, and CMS's own ratings below.
 */
export function RatingCard({
  overallStar,
  adjustedStar,
  adjustReason,
  staffingStar,
  healthStar,
  label,
  scorePct,
  ciLow,
  ciHigh,
  nSurveys,
}: {
  overallStar: number | null | undefined;
  adjustedStar: number | null | undefined;
  adjustReason: string | null | undefined;
  staffingStar: number | null | undefined;
  healthStar: number | null | undefined;
  label: ConsistencyLabel | null;
  scorePct: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  nSurveys: number | null | undefined;
}) {
  const { cms, popQuiz, lowered } = popQuizRating(overallStar, adjustedStar);
  const scored = isScored(scorePct, ciLow, ciHigh);
  const headline = scoreHeadline(scorePct, ciLow, ciHigh, nSurveys);
  const star = (n: number | null | undefined) => (Number.isFinite(n) && (n as number) > 0 ? `${n}★` : "not rated");

  return (
    <section className={`rating-card${lowered ? " is-lowered" : ""}`} aria-labelledby="rating-heading">
      <div className="rating-grid">
        <div className="rating-block">
          <h2 id="rating-heading" className="rating-kicker">Pop Quiz rating</h2>
          {popQuiz !== null ? (
            <p className="rating-stars" aria-label={`${popQuiz} out of 5 stars`}>
              <span aria-hidden>{starString(popQuiz)}</span>
              <span className="rating-num">{popQuiz} of 5</span>
            </p>
          ) : (
            <p className="rating-none">CMS has not published a rating for this home.</p>
          )}
          {lowered ? (
            <>
              <p className="lowered-badge">
                <span aria-hidden>↓</span> Lowered from CMS <s>{cms}★</s> to {popQuiz}★
              </p>
              <p className="rating-why">
                Nurse staffing at this home rises around state inspections more than at a typical
                Georgia home, so inspectors may not see its usual staffing.
              </p>
            </>
          ) : popQuiz !== null ? (
            <p className="same-badge">Same as the CMS rating ({cms}★)</p>
          ) : null}
          {adjustReason ? <p className="meta">{adjustReason}</p> : null}
        </div>

        <div className="rating-block">
          <h3 className="rating-kicker">Staffing change around inspections</h3>
          {scored ? (
            <>
              <p className="pct-big">{formatSignedPct(scorePct as number)}</p>
              <p className="meta">
                range {formatRange(ciLow as number, ciHigh as number)}
                {Number.isFinite(nSurveys) ? ` · ${nSurveys} inspection${nSurveys === 1 ? "" : "s"}` : ""}
              </p>
              <p className="rating-why">{headline}</p>
            </>
          ) : (
            <p className="rating-why">{UNSCORED_COPY}</p>
          )}
          <p className="chip">
            <span className="swatch" style={{ background: label ? LABEL_COLOR[label] : NEUTRAL_COLOR }} aria-hidden />
            {label ? `Staffing consistency: ${label}` : LABEL_PENDING}
          </p>
          {label ? <p className="meta">{LABEL_NOTE[label]}</p> : null}
        </div>
      </div>

      <p className="cms-row">
        CMS Care Compare: {star(overallStar)} overall · {star(staffingStar)} staffing · {star(healthStar)} health
        inspection
      </p>
      <p className="meta">
        How the Pop Quiz rating works: we start from CMS&apos;s overall star rating and take off one star only
        when we&apos;re confident this home&apos;s staffing rises around inspections more than a typical Georgia
        home&apos;s, across at least two inspections. We never add stars. This measures survey-responsive
        staffing, based on PBJ staffing data, which is self-reported.
      </p>
    </section>
  );
}
