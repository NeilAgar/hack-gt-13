import type { PredictabilityRow, ScheduleProb } from "./types";

/** Homes with a positive chance of being chosen, highest probability first. */
export function visibleProbabilities(probs: ScheduleProb[], showAll: boolean): ScheduleProb[] {
  const rows = showAll ? [...probs] : probs.filter((row) => row.prob > 0);
  return rows.sort((a, b) => b.prob - a.prob || a.ccn.localeCompare(b.ccn));
}

/** Internal ranking. Never pass this into a family page. */
export function topPredictability(rows: PredictabilityRow[], limit = 20): PredictabilityRow[] {
  return [...rows].sort((a, b) => b.p_next_60d - a.p_next_60d || a.ccn.localeCompare(b.ccn)).slice(0, limit);
}

/**
 * Default inspections per month for the regulator demo: Georgia's recent pace (about 22 standard
 * inspections a month in CMS survey dates, 2024–2026). The 14 legally overdue homes fill 14 slots, which
 * leaves 8 randomized picks, so Generate shows a different list each time. (The federal target pace is
 * about 28: 356 homes / 12.9 months.)
 */
export const DEFAULT_CAPACITY = 22;
