"use client";

import "leaflet/dist/leaflet.css";
import { Fragment, useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";

import {
  DOT_EDGE_COLOR,
  isConsistencyLabel,
  LABEL_PENDING,
  pinColor,
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

/** Fill radius and ring radius in pixels: a 3.5px consistency ring around the rating fill. */
const FILL_RADIUS = 6.5;
const RING_RADIUS = 10;

function placed(facilities: FacilitySummary[]): FacilitySummary[] {
  return facilities.filter(
    (facility) => Number.isFinite(facility.lat) && Number.isFinite(facility.lon),
  );
}

export default function FacilityMap({ facilities }: { facilities: FacilitySummary[] }) {
  const pins = placed(facilities);
  return (
    <div className="map-frame" role="region" aria-label="Map of nursing homes: dot color is the Pop Quiz rating, ring color is staffing consistency">
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
            <Fragment key={facility.ccn}>
              {/* Outer circle: staffing-consistency ring with a thin dark edge. Carries the tooltip and popup. */}
              <CircleMarker
                center={center}
                radius={RING_RADIUS}
                pathOptions={{
                  color: DOT_EDGE_COLOR,
                  weight: 1,
                  fillColor: pinColor(facility.label, facility.score_pct),
                  fillOpacity: 1,
                }}
              >
                <Tooltip>
                  {facility.name}: {ratingText}
                  {label ? ` · consistency ${label}` : ""}
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
              {/* Inner circle: Pop Quiz rating. Clicks pass through to the ring's popup. */}
              <CircleMarker
                center={center}
                radius={FILL_RADIUS}
                interactive={false}
                pathOptions={{ stroke: false, fillColor: ratingColor(rating.popQuiz), fillOpacity: 1 }}
              />
            </Fragment>
          );
        })}
      </MapContainer>
    </div>
  );
}
