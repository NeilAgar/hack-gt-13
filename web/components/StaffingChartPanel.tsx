"use client";

import { useState } from "react";

import { StaffingChart } from "@/components/StaffingChart";
import type { CurvePoint } from "@/lib/types";

const ONE_WEEK: [number, number] = [-7, 7];
const TWO_WEEKS: [number, number] = [-14, 14];
const FULL: [number, number] = [-42, 56];

/**
 * Simple view first: this home and its normal-day line around the end of inspections, one week
 * each side, with a button to zoom out to two weeks. The full cycle with the Georgia average is
 * in an Advanced section.
 */
export function StaffingChartPanel({
  facilityName,
  curve,
  stateCurve,
  normalP95,
}: {
  facilityName: string;
  curve: CurvePoint[];
  stateCurve: CurvePoint[];
  normalP95: number | null;
}) {
  const [zoomedOut, setZoomedOut] = useState(false);
  const domain = zoomedOut ? TWO_WEEKS : ONE_WEEK;
  const hasLine = typeof normalP95 === "number";

  return (
    <>
      <div className="chart-toolbar">
        <p className="meta">
          Nurse staffing at this home around past inspections, {zoomedOut ? "2 weeks" : "1 week"} before and
          after the day the inspection ended (day 0). Higher means more nurse hours per resident than usual.
        </p>
        <button type="button" className="zoom-button" onClick={() => setZoomedOut((z) => !z)} aria-pressed={zoomedOut}>
          {zoomedOut ? "Zoom in to 1 week" : "Zoom out to 2 weeks"}
        </button>
      </div>
      <StaffingChart
        facilityName={facilityName}
        curve={curve}
        stateCurve={stateCurve}
        normalP95={normalP95}
        xDomain={domain}
        showState={false}
        height={320}
      />
      {hasLine ? (
        <p className="meta">
          Dotted line: this home&apos;s staffing stays below it on 95% of ordinary days. Large dots mark days
          above it.
        </p>
      ) : null}

      <details className="advanced">
        <summary>Advanced: the full inspection cycle and the Georgia average</summary>
        <p className="meta">
          Residual nurse hours per resident day: staffing after removing this home&apos;s usual day-of-week
          pattern, monthly level and 90-day trend. The horizontal axis is days relative to the inspection; day 0
          is the day the inspection ended. The solid line is this home and the dashed line is the Georgia
          average. The score compares days −14 to −1 with days +28 to +56. This describes past inspections, not
          a future visit.
        </p>
        <StaffingChart
          facilityName={facilityName}
          curve={curve}
          stateCurve={stateCurve}
          normalP95={normalP95}
          xDomain={FULL}
          showState
        />
        {hasLine ? (
          <p className="meta">
            The dotted line is the 95th percentile of this home&apos;s staffing on ordinary days (more than 60 days
            from any inspection), averaged over as many days as the home has inspections in this chart. About 1
            ordinary day in 20 crosses it by chance, so look for spikes that cross it right before inspections
            end.
          </p>
        ) : null}
      </details>
    </>
  );
}
