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
