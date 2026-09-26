import type { ConsistencyLabel, CurvePoint } from "./types";

export const LABEL_COLOR: Record<ConsistencyLabel, string> = {
  High: "#1f7a4d",
  Watch: "#b86e00",
  Low: "#a33b32",
};

export const LABEL_NOTE: Record<ConsistencyLabel, string> = {
  High: "Staffing stays steadier across the inspection cycle.",
  Watch: "The pattern is mixed, or the range is too wide to call.",
  Low: "Nurse hours run higher before inspections than afterward.",
};

export function formatPct(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatRange(ciLow: number, ciHigh: number): string {
  return `${formatPct(ciLow)}–${formatPct(ciHigh)}%`;
}

/** Headline required on the facility page. The range is always included. */
export function scoreHeadline(
  scorePct: number,
  ciLow: number,
  ciHigh: number,
  nSurveys: number,
): string {
  const range = `range ${formatRange(ciLow, ciHigh)}`;
  const inspections = `${nSurveys} inspection${nSurveys === 1 ? "" : "s"}`;
  if (scorePct === 0) {
    return `In the 2 weeks before past inspections, nurse hours per resident matched the level a month later (${range}, based on ${inspections}).`;
  }
  const direction = scorePct > 0 ? "higher" : "lower";
  return `In the 2 weeks before past inspections, nurse hours per resident were ${formatPct(Math.abs(scorePct))}% ${direction} than a month later (${range}, based on ${inspections}).`;
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
