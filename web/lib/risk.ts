/**
 * The scheduler's risk weight, mirrored for display. The source of truth is risk_weights() in
 * models/scheduler.py; if the weights change there, change them here too.
 *
 * risk = residents × (0.25 + score/10 + 0.2·harm + 0.4·IJ + |weekend dip|/20 + 2·agency share)
 */
export const RISK_WEIGHTS = {
  base: 0.25,
  scoreDivisor: 10,
  harm: 0.2,
  ij: 0.4,
  weekendDivisor: 20,
  agency: 2,
  /** Used when a home's resident count is missing. */
  defaultResidents: 80,
} as const;

export type RiskInputs = {
  residents?: number | null;
  scorePct?: number | null;
  harm?: number | null;
  ij?: number | null;
  weekendDipPct?: number | null;
  agencyShare?: number | null;
};

const num = (value: number | null | undefined, fallback = 0) =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

/** Same arithmetic as the scheduler: missing inputs count as 0, negative scores count as 0. */
export function riskScore(inputs: RiskInputs): number {
  const w = RISK_WEIGHTS;
  const residents = num(inputs.residents, w.defaultResidents);
  const multiplier =
    w.base +
    Math.max(0, num(inputs.scorePct)) / w.scoreDivisor +
    w.harm * num(inputs.harm) +
    w.ij * num(inputs.ij) +
    Math.abs(num(inputs.weekendDipPct)) / w.weekendDivisor +
    w.agency * Math.max(0, num(inputs.agencyShare));
  return residents * multiplier;
}
