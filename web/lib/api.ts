import fs from "node:fs";
import path from "node:path";

import type {
  BacklogResponse,
  ExplainResponse,
  FacilityDetail,
  FacilitySummary,
  ScheduleRequest,
  ScheduleResponse,
} from "./types";

/**
 * The only data-access module. Calls NEXT_PUBLIC_API_BASE
 * (default http://localhost:8000/api). If that API is unreachable,
 * reads the JSON fixtures in ../fixtures/.
 * Regulator routes send the header X-Demo-Role: regulator.
 */

const DEFAULT_API_BASE = "http://localhost:8000/api";

export class FacilityNotFoundError extends Error {
  constructor(ccn: string) {
    super(`No facility found for CCN ${ccn}.`);
    this.name = "FacilityNotFoundError";
  }
}

class ApiStatusError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`API responded ${status}`);
    this.name = "ApiStatusError";
    this.status = status;
  }
}

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE ?? DEFAULT_API_BASE;
  return configured.replace(/\/$/, "");
}

function fixturesDir(): string {
  const fromWeb = path.join(process.cwd(), "..", "fixtures");
  if (fs.existsSync(fromWeb)) return fromWeb;
  return path.join(process.cwd(), "fixtures");
}

function readFixture<T>(filename: string): T {
  const file = path.join(fixturesDir(), filename);
  return JSON.parse(fs.readFileSync(file, "utf8")) as T;
}

async function request<T>(
  apiPath: string,
  init: RequestInit | undefined,
  regulator: boolean,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (regulator) headers.set("X-Demo-Role", "regulator");

  const timeoutMs = Number(process.env.API_TIMEOUT_MS ?? 4000);
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${apiPath}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : "request failed";
    throw new Error(`API unreachable: ${reason}`);
  }

  if (!response.ok) throw new ApiStatusError(response.status);
  return (await response.json()) as T;
}

async function withFallback<T>(load: () => Promise<T>, fallback: () => T): Promise<T> {
  try {
    return await load();
  } catch (error) {
    if (error instanceof ApiStatusError && error.status < 500) throw error;
    if (error instanceof FacilityNotFoundError) throw error;
    return fallback();
  }
}

function filterFacilities(rows: FacilitySummary[], q: string, limit: number): FacilitySummary[] {
  const query = q.trim().toLowerCase();
  const matched = query
    ? rows.filter(
        (row) =>
          row.name.toLowerCase().includes(query) || row.city.toLowerCase().includes(query),
      )
    : rows;
  return matched.slice(0, limit);
}

export async function getFacilities(q = "", limit = 50): Promise<FacilitySummary[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return withFallback(
    () => request<FacilitySummary[]>(`/facilities?${params.toString()}`, undefined, false),
    () => filterFacilities(readFixture<FacilitySummary[]>("facilities.json"), q, limit),
  );
}

export async function getFacility(ccn: string): Promise<FacilityDetail> {
  try {
    return await withFallback(
      () => request<FacilityDetail>(`/facility/${encodeURIComponent(ccn)}`, undefined, false),
      () => {
        const raw = readFixture<FacilityDetail & { _note?: string }>("facility_sample.json");
        if (raw.ccn !== ccn) throw new FacilityNotFoundError(ccn);
        const { _note: _ignored, ...facility } = raw;
        return facility;
      },
    );
  } catch (error) {
    if (error instanceof ApiStatusError && error.status === 404) throw new FacilityNotFoundError(ccn);
    throw error;
  }
}

export async function explainFacility(ccn: string): Promise<ExplainResponse> {
  return withFallback(
    () =>
      request<ExplainResponse>(
        "/explain",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ccn }),
        },
        false,
      ),
    () => {
      const sampleFacility = readFixture<{ ccn: string }>("facility_sample.json");
      if (sampleFacility.ccn !== ccn) {
        return {
          text: "A plain-language explanation is not available for this home in the offline fixture.",
        };
      }
      return readFixture<ExplainResponse>("explain_sample.json");
    },
  );
}

function assertScheduleRequest(body: ScheduleRequest): void {
  if (!/^\d{4}-\d{2}$/.test(body.month)) {
    throw new Error("Month must be YYYY-MM.");
  }
  if (!Number.isInteger(body.capacity) || body.capacity < 1) {
    throw new Error("Capacity must be a positive integer.");
  }
}

export async function postSchedule(body: ScheduleRequest): Promise<ScheduleResponse> {
  assertScheduleRequest(body);
  const payload: ScheduleRequest = {
    month: body.month,
    capacity: body.capacity,
    ...(body.seed === undefined ? {} : { seed: body.seed }),
  };
  return withFallback(
    () =>
      request<ScheduleResponse>(
        "/schedule",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        true,
      ),
    () => readFixture<ScheduleResponse>("schedule_sample.json"),
  );
}

/** Regulator only. Weeks since each home's last inspection; never call this from family pages. */
export async function getBacklog(): Promise<BacklogResponse> {
  return withFallback(
    () => request<BacklogResponse>("/backlog", undefined, true),
    () => readFixture<BacklogResponse>("backlog_sample.json"),
  );
}
