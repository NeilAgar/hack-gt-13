import type { BacklogHome, ScheduleProb } from "./types";

/** Same constant as models/config.py: weeks in an average month. */
export const WEEKS_PER_MONTH = 365.25 / 12 / 7;

export type BucketId = "recent" | "mid" | "due" | "overdue";

/** Time since the last standard inspection. Overdue uses the scheduler's own forced flag. */
export const BUCKETS: { id: BucketId; label: string; color: string }[] = [
  { id: "recent", label: "0–6 months", color: "#2e9e4f" },
  { id: "mid", label: "6–12 months", color: "#d9a520" },
  { id: "due", label: "12–15.9 months", color: "#d9622b" },
  { id: "overdue", label: "Overdue (15.9+)", color: "#a3232a" },
];

export function monthsSince(weeks: number): number {
  return weeks / WEEKS_PER_MONTH;
}

export function bucketOf(home: BacklogHome): BucketId {
  if (home.forced) return "overdue";
  const months = monthsSince(home.weeks_since_last);
  if (months < 6) return "recent";
  if (months < 12) return "mid";
  return "due";
}

export type BucketSummary = {
  id: BucketId;
  label: string;
  color: string;
  homes: number;
  /** Sum of chances: how many inspections this group is expected to get this month. */
  expectedPicks: number;
  /** Average chance a home in this group is picked this month (0–1). */
  avgChance: number;
};

export function summarizeBacklog(homes: BacklogHome[], probs: ScheduleProb[]): BucketSummary[] {
  const probBy = new Map(probs.map((row) => [row.ccn, row.prob]));
  return BUCKETS.map((bucket) => {
    const members = homes.filter((home) => bucketOf(home) === bucket.id);
    const expectedPicks = members.reduce((sum, home) => sum + (probBy.get(home.ccn) ?? 0), 0);
    return {
      ...bucket,
      homes: members.length,
      expectedPicks,
      avgChance: members.length ? expectedPicks / members.length : 0,
    };
  });
}

/**
 * Homes that are not overdue now but cross the 15.9-month line within a month, and how many of them
 * are expected to stay uninspected this month (sum of 1 − chance) and so become overdue next month.
 */
export function nextMonthOverdue(homes: BacklogHome[], probs: ScheduleProb[], forcedWeeks: number) {
  const probBy = new Map(probs.map((row) => [row.ccn, row.prob]));
  const crossing = homes.filter((home) => !home.forced && home.weeks_since_last + WEEKS_PER_MONTH >= forcedWeeks);
  const expectedOverdue = crossing.reduce((sum, home) => sum + (1 - (probBy.get(home.ccn) ?? 0)), 0);
  return { crossing: crossing.length, expectedOverdue };
}

/** One dot per home: months since the last inspection vs. chance of being picked this month. */
export function scatterPoints(homes: BacklogHome[], probs: ScheduleProb[]) {
  const probBy = new Map(probs.map((row) => [row.ccn, row.prob]));
  return homes
    .filter((home) => probBy.has(home.ccn))
    .map((home) => ({
      ccn: home.ccn,
      bucket: bucketOf(home),
      months: Math.round(monthsSince(home.weeks_since_last) * 10) / 10,
      chance: Math.round((probBy.get(home.ccn) ?? 0) * 1000) / 10,
    }));
}
