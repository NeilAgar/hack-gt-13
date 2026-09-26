import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RatingCard } from "@/components/RatingCard";
import { StaffingChartPanel } from "@/components/StaffingChartPanel";
import { explainFacility, FacilityNotFoundError, getFacilities, getFacility } from "@/lib/api";
import { isConsistencyLabel } from "@/lib/format";
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
  const score = facility?.score_pct ?? summary?.score_pct ?? null;
  const ciLow = facility?.ci_low ?? summary?.ci_low ?? null;
  const ciHigh = facility?.ci_high ?? summary?.ci_high ?? null;

  return (
    <>
      <a className="back" href="/">
        ← All homes
      </a>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        {place}
      </p>
      <h1>{name}</h1>
      <RatingCard
        overallStar={facility?.overall_star ?? summary?.overall_star}
        adjustedStar={facility?.adjusted_star ?? summary?.adjusted_star}
        adjustReason={facility?.adjust_reason}
        staffingStar={facility?.staffing_star ?? summary?.staffing_star}
        healthStar={facility?.health_star}
        label={label}
        scorePct={score}
        ciLow={ciLow}
        ciHigh={ciHigh}
        nSurveys={facility?.n_surveys}
      />
      <p className="note">PBJ staffing data is self-reported.</p>

      <div className="stack">
        <section className="panel" aria-labelledby="curve-heading">
          <h2 id="curve-heading">Staffing across the inspection cycle</h2>
          {facility && (facility.curve ?? []).some((point) => Number.isFinite(point?.d) && Number.isFinite(point?.v)) ? (
            <StaffingChartPanel
              facilityName={facility.name}
              curve={facility.curve ?? []}
              stateCurve={facility.state_curve ?? []}
              normalP95={facility.normal_p95 ?? null}
            />
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
