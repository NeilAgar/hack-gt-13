"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";

import {
  DOT_EDGE_COLOR,
  isConsistencyLabel,
  LABEL_PENDING,
  popQuizRating,
  ratingColor,
  scoreSummary,
} from "@/lib/format";
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

/** Dot radius in pixels. The dot is the Pop Quiz rating only; consistency is on the list and facility page. */
const DOT_RADIUS = 8;

function placed(facilities: FacilitySummary[]): FacilitySummary[] {
  return facilities.filter(
    (facility) => Number.isFinite(facility.lat) && Number.isFinite(facility.lon),
  );
}

export default function FacilityMap({ facilities }: { facilities: FacilitySummary[] }) {
  const pins = placed(facilities);
  return (
    <div className="map-frame" role="region" aria-label="Map of nursing homes: dot color is the Pop Quiz rating">
      <MapContainer center={[32.7, -83.4]} zoom={7} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds facilities={pins} />
        {pins.map((facility) => {
          const label = isConsistencyLabel(facility.label) ? facility.label : null;
          const rating = popQuizRating(facility.overall_star, facility.adjusted_star);
          const center: [number, number] = [facility.lat, facility.lon];
          const ratingText =
            rating.popQuiz === null
              ? "Not rated by CMS"
              : `Pop Quiz ${rating.popQuiz}★${rating.lowered ? ` (lowered from CMS ${rating.cms}★)` : ""}`;
          return (
            <CircleMarker
              key={facility.ccn}
              center={center}
              radius={DOT_RADIUS}
              pathOptions={{
                color: DOT_EDGE_COLOR,
                weight: 1,
                fillColor: ratingColor(rating.popQuiz),
                fillOpacity: 1,
              }}
            >
              <Tooltip>
                {facility.name}: {ratingText}
              </Tooltip>
              <Popup>
                <strong>{facility.name}</strong>
                <br />
                {facility.city}
                <br />
                {ratingText} · CMS Care Compare {facility.overall_star}★
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
