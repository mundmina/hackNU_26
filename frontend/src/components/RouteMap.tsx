import "leaflet/dist/leaflet.css";

import { MapContainer, Marker, Polyline, TileLayer, Tooltip } from "react-leaflet";

interface RouteMapProps {
  position: [number, number] | null;
  speedLimit: number;
  gradient: number;
}

export function RouteMap({ position, speedLimit, gradient }: RouteMapProps) {
  const fallback: [number, number] = position ?? [43.238949, 76.889709];
  const route: [number, number][] = [
    [fallback[0] - 0.05, fallback[1] - 0.08],
    [fallback[0] - 0.02, fallback[1] - 0.03],
    fallback,
    [fallback[0] + 0.03, fallback[1] + 0.06],
  ];

  return (
    <section className="panel map-panel">
      <div className="panel-header">
        <p>Route Context</p>
        <span className="muted">
          Limit {speedLimit} km/h, gradient {gradient.toFixed(1)}‰
        </span>
      </div>
      <div className="map-shell">
        <MapContainer center={fallback} zoom={8} scrollWheelZoom={false} className="leaflet-map">
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <Polyline positions={route} pathOptions={{ color: "#f2b94b", weight: 5 }} />
          <Marker position={fallback}>
            <Tooltip direction="top" offset={[0, -12]} opacity={1}>
              Current locomotive
            </Tooltip>
          </Marker>
        </MapContainer>
      </div>
    </section>
  );
}
