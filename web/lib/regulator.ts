import type { ScheduleProb } from "./types";

/** Homes with a positive chance of being chosen, highest probability first. */
export function visibleProbabilities(probs: ScheduleProb[], showAll: boolean): ScheduleProb[] {
  const rows = showAll ? [...probs] : probs.filter((row) => row.prob > 0);
  return rows.sort((a, b) => b.prob - a.prob || a.ccn.localeCompare(b.ccn));
}

/**
 * Default inspections per month for the regulator demo: Georgia's recent pace (about 22 standard
 * inspections a month in CMS survey dates, 2024–2026). The 14 legally overdue homes fill 14 slots, which
 * leaves 8 randomized picks, so Generate shows a different list each time. (The federal target pace is
 * about 28: 356 homes / 12.9 months.)
 */
export const DEFAULT_CAPACITY = 22;

/** Homes the schedule must include by law (more than 15.9 months since their last standard inspection). */
export function overdueCount(schedule: { probs: { forced: boolean }[] } | null | undefined): number {
  return schedule ? schedule.probs.filter((row) => row.forced).length : 0;
}

/** Keep a typed capacity whole and at or above the minimum. */
export function clampCapacity(value: number, min: number, max = Number.POSITIVE_INFINITY): number {
  const n = Number.isFinite(value) ? Math.round(value) : min;
  return Math.min(max, Math.max(min, n));
}
