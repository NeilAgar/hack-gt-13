/**
 * The scheduler's risk weight, mirrored for display. The source of truth is risk_weights() in
 * models/scheduler.py; if the weights change there, change them here too.
 *
 * risk = residents × (0.25 + 1 × S + 1 × C + 2 × T)
 *   S = the home's percentile (0–1) among Georgia homes on its survey-responsive score
 *   C = min(1, 0.1 × harm citations + 0.2 × immediate-jeopardy citations), last 3 years
 *   T = time since the last standard inspection: 0 until 12 months, rising linearly to 1 at 15.9 months
 */
export const RISK_WEIGHTS = {
  base: 0.25,
  score: 1,
  citations: 1,
  time: 2,
  timeStartMonths: 12,
  timeFullMonths: 15.9,
  harmPoints: 0.1,
  ijPoints: 0.2,
  /** Used when a home's resident count is missing. */
  defaultResidents: 80,
  /** Used when a home has no score: the middle of Georgia, not the top or bottom. */
  missingPercentile: 0.5,
} as const;

export type RiskInputs = {
  residents?: number | null;
  /** 0–1: share of Georgia homes with a lower survey-responsive score. */
  scorePercentile?: number | null;
  harm?: number | null;
  ij?: number | null;
  /** Months since the last standard inspection. */
  monthsSinceLast?: number | null;
};

const finite = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value);

/** Citation signal: 0.1 per harm citation, 0.2 per immediate-jeopardy citation, capped at 1. */
export function citationSignal(harm?: number | null, ij?: number | null): number {
  const w = RISK_WEIGHTS;
  return Math.min(1, w.harmPoints * (finite(harm) ? harm : 0) + w.ijPoints * (finite(ij) ? ij : 0));
}

/** Time signal: 0 until 12 months since the last inspection, 1 at the 15.9-month legal limit. */
export function timeSignal(monthsSinceLast?: number | null): number {
  const w = RISK_WEIGHTS;
  if (!finite(monthsSinceLast)) return 0;
  const t = (monthsSinceLast - w.timeStartMonths) / (w.timeFullMonths - w.timeStartMonths);
  return Math.min(1, Math.max(0, t));
}

/** Same arithmetic as the scheduler. */
export function riskScore(inputs: RiskInputs): number {
  const w = RISK_WEIGHTS;
  const residents = finite(inputs.residents) ? inputs.residents : w.defaultResidents;
  const s = finite(inputs.scorePercentile) ? inputs.scorePercentile : w.missingPercentile;
  const c = citationSignal(inputs.harm, inputs.ij);
  const t = timeSignal(inputs.monthsSinceLast);
  return residents * (w.base + w.score * s + w.citations * c + w.time * t);
}
