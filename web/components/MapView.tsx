"use client";

import dynamic from "next/dynamic";

import type { FacilitySummary } from "@/lib/types";

const FacilityMap = dynamic(() => import("@/components/FacilityMap"), {
  ssr: false,
  loading: () => <div className="map-frame map-loading">Loading map…</div>,
});

export function MapView({ facilities }: { facilities: FacilitySummary[] }) {
  return <FacilityMap facilities={facilities} />;
}
