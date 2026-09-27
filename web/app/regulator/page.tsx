import type { Metadata } from "next";

import { DEFAULT_CAPACITY, overdueCount } from "@/lib/regulator";
import { RiskPanel } from "@/components/RiskPanel";
import { SchedulePanel } from "@/components/SchedulePanel";
import { getBacklog, getFacilities, postSchedule } from "@/lib/api";
import { currentMonth } from "@/lib/format";
import type { BacklogResponse, ScheduleRequest, ScheduleResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

// Inspector/admin view: not linked from the site navigation, and kept out of search engines.
export const metadata: Metadata = {
  title: "Regulator demo · StaffTrace",
  robots: { index: false, follow: false },
};

async function generateSchedule(body: ScheduleRequest): Promise<ScheduleResponse> {
  "use server";
  return postSchedule(body);
}

export default async function RegulatorPage() {
  const [facilities, backlog] = await Promise.all([
    getFacilities("", 400),
    getBacklog().catch((): BacklogResponse | null => null),
  ]);
  const names = Object.fromEntries(facilities.map((facility) => [facility.ccn, facility.name]));
  // The schedule marks every legally overdue home as forced; that count is the smallest usable capacity.
  let overdue = 0;
  let initialSchedule: ScheduleResponse | null = null;
  try {
    initialSchedule = await postSchedule({ month: currentMonth(), capacity: DEFAULT_CAPACITY, seed: 0 });
    overdue = overdueCount(initialSchedule);
  } catch {
    overdue = 0;
  }
  const minCapacity = Math.max(1, overdue);

  return (
    <>
      <p className="eyebrow" style={{ color: "var(--muted)" }}>
        Regulator demo
      </p>
      <h1>Survey agency view</h1>
      <p className="lede">
        Plan this month&apos;s standard inspections. The list is randomized and weighted by risk, so a home
        can&apos;t tell when its next visit is coming, and every legally overdue home is always included.
        Risk uses survey-responsive staffing, which is based on PBJ staffing data. PBJ staffing data is
        self-reported.
      </p>

      <RiskPanel />
      <SchedulePanel
        generateSchedule={generateSchedule}
        minCapacity={minCapacity}
        overdue={overdue}
        names={names}
        backlog={backlog}
        initialSchedule={initialSchedule}
      />
    </>
  );
}
