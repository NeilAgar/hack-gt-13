/** Response types for docs/CONTRACTS.md v1. Percentages are percent units (11.2 means 11.2%). */

export type ConsistencyLabel = "High" | "Watch" | "Low";

/** GET /facilities. Score and label are null until the pipeline has both. */
export type FacilitySummary = {
  ccn: string;
  name: string;
  city: string;
  lat: number;
  lon: number;
  overall_star: number;
  /** v1.1: CMS overall rating minus one star for clear, repeated survey-responsive staffing. */
  adjusted_star?: number | null;
  staffing_star: number;
  score_pct: number | null;
  ci_low: number | null;
  ci_high: number | null;
  label: ConsistencyLabel | null;
  trophy_flag: boolean;
};

/** Curve point: rel_day and residual HPRD. */
export type CurvePoint = {
  d: number;
  v: number;
};

/**
 * GET /facility/{ccn}
 * Facility fields, score fields, curves, and an optional stored explanation.
 */
export type FacilityDetail = {
  ccn: string;
  name: string;
  city: string;
  county: string;
  lat: number;
  lon: number;
  certified_beds: number;
  avg_residents: number;
  ownership: string;
  overall_star: number;
  staffing_star: number;
  health_star: number;
  harm_citations_3y: number;
  ij_citations_3y: number;
  rbs_proxy_eligible: boolean;
  n_surveys: number | null;
  raw_pct: number | null;
  score_pct: number | null;
  ci_low: number | null;
  ci_high: number | null;
  surge_pct: number | null;
  weekend_dip_pct: number | null;
  label: ConsistencyLabel | null;
  trophy_flag: boolean;
  curve: CurvePoint[];
  state_curve: CurvePoint[];
  explanation: string | null;
  /** v1.1: StaffTrace rating and the plain-language reason for it. */
  adjusted_star?: number | null;
  adjust_reason?: string | null;
  /** v1.2: this home's normal-day line, same units as curve.v (95th percentile of ordinary days). */
  normal_p95?: number | null;
  /** v1.2: ordinary days (more than 60 days from any inspection) the line is based on. */
  normal_days?: number | null;
};

/** POST /explain */
export type ExplainRequest = {
  ccn: string;
};

export type ExplainResponse = {
  text: string;
};

/** POST /schedule */
export type ScheduleRequest = {
  month: string;
  capacity: number;
  seed?: number;
};

export type ScheduleSelected = {
  ccn: string;
  name: string;
  prob: number;
  forced: boolean;
  off_hours: boolean;
};

export type ScheduleProb = {
  ccn: string;
  prob: number;
  forced: boolean;
};

export type ScheduleResponse = {
  month: string;
  capacity: number;
  selected: ScheduleSelected[];
  probs: ScheduleProb[];
};

/** GET /trophy */
export type TrophyRow = {
  ccn: string;
  name: string;
  overall_star: number;
  score_pct: number | null;
  ci_low: number | null;
};
