"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";

import { formatPct, formatRange, LABEL_COLOR } from "@/lib/format";
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

export default function FacilityMap({ facilities }: { facilities: FacilitySummary[] }) {
  return (
    <div className="map-frame" role="region" aria-label="Map of nursing homes colored by staffing consistency">
      <MapContainer center={[32.7, -83.4]} zoom={7} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds facilities={facilities} />
        {facilities.map((facility) => (
          <CircleMarker
            key={facility.ccn}
            center={[facility.lat, facility.lon]}
            radius={10}
            pathOptions={{
              color: "#fffdf9",
              weight: 2,
              fillColor: LABEL_COLOR[facility.label],
              fillOpacity: 1,
            }}
          >
            <Tooltip>
              {facility.name}: {facility.label}
            </Tooltip>
            <Popup>
              <strong>{facility.name}</strong>
              <br />
              {facility.city} · Care Compare {facility.overall_star}★
              <br />
              Staffing consistency: {facility.label}
              <br />
              {formatPct(facility.score_pct)}% (range {formatRange(facility.ci_low, facility.ci_high)})
              <br />
              <a href={`/facility/${facility.ccn}`}>Open home</a>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
