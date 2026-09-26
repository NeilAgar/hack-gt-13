import type { ConsistencyLabel, CurvePoint } from "./types";

export const LABEL_COLOR: Record<ConsistencyLabel, string> = {
  High: "#1f7a4d",
  Watch: "#b86e00",
  Low: "#a33b32",
};

/** Pins and chips with no score or no High/Watch/Low label. */
export const NEUTRAL_COLOR = "#8a8478";

export const LABEL_PENDING = "Label pending";

export const UNSCORED_COPY =
  "Not enough inspections with staffing data to score this home yet.";

export const LABEL_NOTE: Record<ConsistencyLabel, string> = {
  High: "Staffing stays steadier across the inspection cycle.",
  Watch: "The pattern is mixed, or the range is too wide to call.",
  Low: "Nurse hours run higher through the end of an inspection than a month later.",
};

export function isConsistencyLabel(value: string | null | undefined): value is ConsistencyLabel {
  return value === "High" || value === "Watch" || value === "Low";
}

export function isScored(
  scorePct: number | null | undefined,
  ciLow: number | null | undefined,
  ciHigh: number | null | undefined,
): boolean {
  return Number.isFinite(scorePct) && Number.isFinite(ciLow) && Number.isFinite(ciHigh);
}

/** Grey when the home has no score or the consistency label is not set. */
export function pinColor(
  label: string | null | undefined,
  scorePct: number | null | undefined,
): string {
  if (!Number.isFinite(scorePct) || !isConsistencyLabel(label)) return NEUTRAL_COLOR;
  return LABEL_COLOR[label];
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

export function formatPct(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatRange(ciLow: number, ciHigh: number): string {
  return `${formatPct(ciLow)}–${formatPct(ciHigh)}%`;
}

/**
 * Facility-page headline. Day 0 is the inspection end date, so the scored
 * window (days −14 through −1) includes days the surveyors were in the building.
 * Returns null when the home has no score.
 */
export function scoreHeadline(
  scorePct: number | null | undefined,
  ciLow: number | null | undefined,
  ciHigh: number | null | undefined,
  nSurveys: number | null | undefined,
): string | null {
  if (!isScored(scorePct, ciLow, ciHigh)) return null;
  const range = `range ${formatRange(ciLow as number, ciHigh as number)}`;
  const based = Number.isFinite(nSurveys)
    ? `, based on ${nSurveys} inspection${nSurveys === 1 ? "" : "s"}`
    : "";
  const window = "In the 14 days through the day before past inspections ended";
  if (scorePct === 0) {
    return `${window}, nurse hours per resident matched the level a month later (${range}${based}).`;
  }
  const direction = (scorePct as number) > 0 ? "higher" : "lower";
  return `${window}, nurse hours per resident were ${formatPct(Math.abs(scorePct as number))}% ${direction} than a month later (${range}${based}).`;
}

export function scoreSummary(
  scorePct: number | null | undefined,
  ciLow: number | null | undefined,
  ciHigh: number | null | undefined,
): string {
  if (!isScored(scorePct, ciLow, ciHigh)) return UNSCORED_COPY;
  return `${formatPct(scorePct as number)}% (range ${formatRange(ciLow as number, ciHigh as number)})`;
}

/**
 * The simulation holds staffing behavior fixed and only changes who is inspected,
 * so a few percent is the short-run result. Show that percent next to the counts.
 */
export function reductionCaption(reductionPct: number | null | undefined): string | null {
  if (!Number.isFinite(reductionPct)) return null;
  const pct = reductionPct as number;
  const amount = `${formatPct(Math.abs(pct))}%`;
  if (pct < 0) {
    return `This capacity leaves ${amount} more undetected shirk resident-months than the status quo. The gap turns the other way when the monthly budget is closer to a usual survey count.`;
  }
  if (pct < 10) {
    return `${amount} fewer undetected shirk resident-months. That is a small short-run gap: homes in this model still staff to the historical 40–60 week window, and only which homes are inspected changes.`;
  }
  return `${amount} fewer undetected shirk resident-months than the status quo, at the same inspector budget. Homes in this model still staff to the historical 40–60 week window.`;
}

export function mergeCurves(facility: CurvePoint[], state: CurvePoint[]) {
  const days = Array.from(
    new Set([...facility.map((point) => point.d), ...state.map((point) => point.d)]),
  ).sort((a, b) => a - b);
  const facilityByDay = new Map(facility.map((point) => [point.d, point.v]));
  const stateByDay = new Map(state.map((point) => [point.d, point.v]));
  return days.map((d) => ({
    d,
    facility: facilityByDay.get(d) ?? null,
    state: stateByDay.get(d) ?? null,
  }));
}

export function currentMonth(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

export function formatProbability(prob: number): string {
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(prob * 100)}%`;
}
