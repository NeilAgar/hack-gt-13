import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StaffingChart } from "@/components/StaffingChart";
import { explainFacility, FacilityNotFoundError, getFacilities, getFacility } from "@/lib/api";
import { formatPct, formatRange, LABEL_COLOR, scoreHeadline } from "@/lib/format";
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
  const label = facility?.label ?? summary?.label ?? "Watch";
  const overall = facility?.overall_star ?? summary?.overall_star ?? 0;
  const staffing = facility?.staffing_star ?? summary?.staffing_star ?? 0;
  const score = facility?.score_pct ?? summary?.score_pct ?? 0;
  const ciLow = facility?.ci_low ?? summary?.ci_low ?? 0;
  const ciHigh = facility?.ci_high ?? summary?.ci_high ?? 0;

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
          <span className="swatch" style={{ background: LABEL_COLOR[label] }} aria-hidden />
          Staffing consistency: {label}
        </span>
      </p>
      {facility ? (
        <p className="score-headline">
          {scoreHeadline(facility.score_pct, facility.ci_low, facility.ci_high, facility.n_surveys)}
        </p>
      ) : (
        <p className="score-headline">
          {score === 0
            ? `Nurse hours per resident in the 2 weeks before past inspections matched the level a month later (range ${formatRange(ciLow, ciHigh)}). `
            : `Nurse hours per resident were ${formatPct(Math.abs(score))}% ${score > 0 ? "higher" : "lower"} in the 2 weeks before past inspections than a month later (range ${formatRange(ciLow, ciHigh)}). `}
          The number of inspections behind this score is not in the current record.
        </p>
      )}
      <div className="stat-row">
        <div className="stat">
          <b>{formatPct(score)}%</b>
          <span>Score</span>
        </div>
        <div className="stat">
          <b>{formatRange(ciLow, ciHigh)}</b>
          <span>Uncertainty range</span>
        </div>
        {facility ? (
          <div className="stat">
            <b>{facility.n_surveys}</b>
            <span>Past inspections in the score</span>
          </div>
        ) : null}
      </div>
      <p>
        This score measures survey-responsive staffing: the percent difference in nurse hours per
        resident before past inspections versus a month later.
      </p>
      <p className="note">PBJ staffing data is self-reported.</p>

      <div className="stack">
        <section className="panel" aria-labelledby="curve-heading">
          <h2 id="curve-heading">Staffing across the inspection cycle</h2>
          {facility && (facility.curve ?? []).some((point) => Number.isFinite(point?.d) && Number.isFinite(point?.v)) ? (
            <>
              <p className="meta">
                Residual nurse hours per resident day. The horizontal axis is days relative to the
                inspection. Day 0 is the inspection. The solid line is this home and the dashed line is
                the Georgia average. This describes past inspections, not a future visit.
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
