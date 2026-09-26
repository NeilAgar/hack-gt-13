"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";

import { isConsistencyLabel, LABEL_PENDING, pinColor, scoreSummary } from "@/lib/format";
import type { FacilitySummary } from "@/lib/types";

function FitBounds({ facilities }: { facilities: FacilitySummary[] }) {
  const map = useMap();
  useEffect(() => {
    if (facilities.length === 0) return;
    map.fitBounds(
      facilities.map((facility) => [facility.lat, facility.lon] as [number, number]),
      { padding: [28, 28], maxZoom: 11 },
    );
  }, [facilities, map]);
  return null;
}

function placed(facilities: FacilitySummary[]): FacilitySummary[] {
  return facilities.filter(
    (facility) => Number.isFinite(facility.lat) && Number.isFinite(facility.lon),
  );
}

export default function FacilityMap({ facilities }: { facilities: FacilitySummary[] }) {
  const pins = placed(facilities);
  return (
    <div className="map-frame" role="region" aria-label="Map of nursing homes colored by staffing consistency">
      <MapContainer center={[32.7, -83.4]} zoom={7} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds facilities={pins} />
        {pins.map((facility) => {
          const label = isConsistencyLabel(facility.label) ? facility.label : null;
          return (
          <CircleMarker
            key={facility.ccn}
            center={[facility.lat, facility.lon]}
            radius={8}
            pathOptions={{
              color: "#fffdf9",
              weight: 2,
              fillColor: pinColor(facility.label, facility.score_pct),
              fillOpacity: 1,
            }}
          >
            <Tooltip>
              {facility.name}
              {label ? `: ${label}` : ""}
            </Tooltip>
            <Popup>
              <strong>{facility.name}</strong>
              <br />
              {facility.city} · Care Compare {facility.overall_star}★
              <br />
              {label ? `Staffing consistency: ${label}` : LABEL_PENDING}
              <br />
              {scoreSummary(facility.score_pct, facility.ci_low, facility.ci_high)}
              <br />
              <a href={`/facility/${facility.ccn}`}>Open home</a>
            </Popup>
          </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
