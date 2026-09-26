import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StaffingChart } from "@/components/StaffingChart";
import { explainFacility, FacilityNotFoundError, getFacilities, getFacility } from "@/lib/api";
import {
  formatPct,
  formatRange,
  isConsistencyLabel,
  isScored,
  LABEL_COLOR,
  LABEL_PENDING,
  NEUTRAL_COLOR,
  scoreHeadline,
  UNSCORED_COPY,
} from "@/lib/format";
import type { FacilityDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

const TOUR_QUESTIONS = [
  "How does weekend staffing compare with weekdays?",
  "What share of nurse hours comes from agency staff?",
  "Is a registered nurse on site at night?",
];

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ccn: string }>;
}): Promise<Metadata> {
  const { ccn } = await params;
  return { title: `Facility ${ccn} · Pop Quiz` };
}

export default async function FacilityPage({
  params,
}: {
  params: Promise<{ ccn: string }>;
}) {
  const { ccn } = await params;

  let facility: FacilityDetail | null = null;
  try {
    facility = await getFacility(ccn);
  } catch (error) {
    if (!(error instanceof FacilityNotFoundError)) throw error;
  }

  const summary = facility
    ? null
    : (await getFacilities("", 500)).find((row) => row.ccn === ccn) ?? null;

  if (!facility && !summary) notFound();

  let explanation: string | null = facility?.explanation ?? null;
  try {
    const explained = await explainFacility(ccn);
    if (explained.text.trim()) explanation = explained.text;
  } catch {
    explanation = facility?.explanation ?? null;
  }

  const name = facility?.name ?? summary?.name ?? "Nursing home";
  const city = facility?.city ?? summary?.city ?? "";
  const place = facility?.county ? `${city}, ${facility.county}` : city;
  const rawLabel = facility?.label ?? summary?.label;
  const label = isConsistencyLabel(rawLabel) ? rawLabel : null;
  const overall = facility?.overall_star ?? summary?.overall_star ?? 0;
  const staffing = facility?.staffing_star ?? summary?.staffing_star ?? 0;
  const score = facility?.score_pct ?? summary?.score_pct ?? null;
  const ciLow = facility?.ci_low ?? summary?.ci_low ?? null;
  const ciHigh = facility?.ci_high ?? summary?.ci_high ?? null;
  const scored = isScored(score, ciLow, ciHigh);
  const headline = scoreHeadline(score, ciLow, ciHigh, facility?.n_surveys);

  return (
    <>
      <a className="back" href="/">
        ← All homes
      </a>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        {place}
      </p>
      <h1>{name}</h1>
      <p className="meta">
        Care Compare {overall}★ overall · {staffing}★ staffing
        {facility && Number.isFinite(facility.health_star)
          ? ` · ${facility.health_star}★ health inspection`
          : ""}
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
      {scored && headline ? (
        <p className="score-headline">
          {headline}
          {facility ? "" : " The number of inspections behind this score is not in the current record."}
        </p>
      ) : (
        <p className="score-headline">{UNSCORED_COPY}</p>
      )}
      {scored ? (
        <div className="stat-row">
          <div className="stat">
            <b>{formatPct(score as number)}%</b>
            <span>Score</span>
          </div>
          <div className="stat">
            <b>{formatRange(ciLow as number, ciHigh as number)}</b>
            <span>Uncertainty range</span>
          </div>
          {facility && Number.isFinite(facility.n_surveys) ? (
            <div className="stat">
              <b>{facility.n_surveys}</b>
              <span>Past inspections in the score</span>
            </div>
          ) : null}
        </div>
      ) : null}
      {scored ? (
        <p>
          This score measures survey-responsive staffing: the percent difference in nurse hours per
          resident between the 14 days through the day before an inspection ended and about a month
          later.
        </p>
      ) : null}
      <p className="note">PBJ staffing data is self-reported.</p>

      <div className="stack">
        <section className="panel" aria-labelledby="curve-heading">
          <h2 id="curve-heading">Staffing across the inspection cycle</h2>
          {facility && (facility.curve ?? []).some((point) => Number.isFinite(point?.d) && Number.isFinite(point?.v)) ? (
            <>
              <p className="meta">
                Residual nurse hours per resident day. The horizontal axis is days relative to the
                inspection. Day 0 is the day the inspection ended. The solid line is this home and the
                dashed line is the Georgia average. This describes past inspections, not a future visit.
              </p>
              <StaffingChart
                facilityName={facility.name}
                curve={facility.curve ?? []}
                stateCurve={facility.state_curve ?? []}
              />
            </>
          ) : (
            <p>not enough inspections</p>
          )}
        </section>

        <section className="panel" aria-labelledby="explain-heading">
          <h2 id="explain-heading">Plain-language explanation</h2>
          <p>
            {explanation?.trim()
              ? explanation
              : "A plain-language explanation is not available for this home yet."}
          </p>
        </section>

        <section className="panel" aria-labelledby="tour-heading">
          <h2 id="tour-heading">Questions to ask on a tour</h2>
          <ul className="questions">
            {TOUR_QUESTIONS.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
