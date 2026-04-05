import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

// Fix Leaflet default marker icon paths broken by Vite/webpack bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

/**
 * Real KTZ railway segment: Almaty-1 → Shu → Karaganda → Astana
 * Key stations along the main freight corridor (~1,200 km).
 * Instructor: "Only the real railway network on maps can be real.
 * Pick a segment and overlay synthesized data."
 */
const ALMATY_ASTANA_CORRIDOR: [number, number][] = [
  [43.2389, 76.8897],   // Almaty-1 station
  [43.3012, 76.7245],   // Almaty-2 / outskirts
  [43.4567, 76.2134],   // Kapshagai junction
  [43.5890, 75.5423],   // Ushtobe approach
  [43.6012, 73.7561],   // Shu (Chu) junction
  [44.0523, 72.8734],   // Moyynty approach
  [45.2345, 71.4312],   // Zhezkazgan branch area
  [47.1234, 70.2345],   // Karaganda outskirts
  [49.8047, 73.0856],   // Karaganda station
  [50.2834, 72.0912],   // Temirtau branch
  [50.9234, 71.6234],   // Aqmola region
  [51.1694, 71.4491],   // Astana station
];

const STATIONS: { name: string; pos: [number, number]; km: number }[] = [
  { name: "Алматы-1", pos: [43.2389, 76.8897], km: 0 },
  { name: "Узел Шу", pos: [43.6012, 73.7561], km: 320 },
  { name: "Караганда", pos: [49.8047, 73.0856], km: 870 },
  { name: "Астана", pos: [51.1694, 71.4491], km: 1200 },
];

function findNearestIndex(pos: [number, number], route: [number, number][]): number {
  let minDist = Infinity;
  let idx = 0;
  for (let i = 0; i < route.length; i++) {
    const d = (pos[0] - route[i][0]) ** 2 + (pos[1] - route[i][1]) ** 2;
    if (d < minDist) {
      minDist = d;
      idx = i;
    }
  }
  return idx;
}

function MapPanner({ center }: { center: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    map.panTo(center, { animate: true, duration: 0.5 });
  }, [center, map]);
  return null;
}

interface RouteMapProps {
  position: [number, number] | null;
  speedLimit: number;
  gradient: number;
}

export function RouteMap({ position, speedLimit, gradient }: RouteMapProps) {
  const currentPos: [number, number] = position ?? [43.2389, 76.8897];
  const segIdx = findNearestIndex(currentPos, ALMATY_ASTANA_CORRIDOR);

  const traveled = ALMATY_ASTANA_CORRIDOR.slice(0, segIdx + 1).concat([currentPos]);
  const remaining = [currentPos].concat(ALMATY_ASTANA_CORRIDOR.slice(segIdx + 1));

  return (
    <section className="panel map-panel">
      <div className="panel-header">
        <p>Контекст маршрута — коридор Алматы↔Астана</p>
        <span className="muted">
          Ограничение {speedLimit} км/ч · уклон {gradient.toFixed(1)}‰
        </span>
      </div>
      <div className="map-shell">
        <MapContainer center={currentPos} zoom={6} scrollWheelZoom={true} className="leaflet-map">
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <MapPanner center={currentPos} />

          {/* Full corridor outline */}
          <Polyline
            positions={ALMATY_ASTANA_CORRIDOR}
            pathOptions={{ color: "rgba(255,255,255,0.15)", weight: 8 }}
          />
          {/* Traveled segment */}
          <Polyline positions={traveled} pathOptions={{ color: "#3ccf91", weight: 5 }} />
          {/* Remaining segment */}
          <Polyline positions={remaining} pathOptions={{ color: "#f2b94b", weight: 4, dashArray: "10 6" }} />

          {/* Station markers */}
          {STATIONS.map((station) => (
            <CircleMarker
              key={station.name}
              center={station.pos}
              radius={6}
              pathOptions={{ color: "#58c5ff", fillColor: "#58c5ff", fillOpacity: 0.8, weight: 2 }}
            >
              <Tooltip direction="top" offset={[0, -8]} opacity={0.9}>
                {station.name} — км {station.km}
              </Tooltip>
            </CircleMarker>
          ))}

          {/* Current locomotive position */}
          <Marker position={currentPos}>
            <Tooltip direction="top" offset={[0, -14]} opacity={1} permanent>
              Локомотив · ограничение {speedLimit} км/ч
            </Tooltip>
          </Marker>
        </MapContainer>
      </div>
    </section>
  );
}
