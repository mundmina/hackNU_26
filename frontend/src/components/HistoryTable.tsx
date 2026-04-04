import type { EnrichedTelemetry } from "../types";

interface HistoryTableProps {
  history: EnrichedTelemetry[];
}

export function HistoryTable({ history }: HistoryTableProps) {
  return (
    <section className="panel history-panel">
      <div className="panel-header">
        <p>Telemetry History</p>
        <span className="muted">Recent persisted events</span>
      </div>
      <div className="history-table">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Speed</th>
              <th>Slip</th>
              <th>Oil</th>
              <th>Brake</th>
              <th>HI</th>
            </tr>
          </thead>
          <tbody>
            {history.slice(0, 12).map((item) => (
              <tr key={item.event_id}>
                <td>{new Date(item.telemetry.timestamp).toLocaleTimeString()}</td>
                <td>{item.telemetry.speed_kmh.toFixed(1)}</td>
                <td>{item.telemetry.wheel_slip_ratio_pct.toFixed(2)}%</td>
                <td>{item.telemetry.engine_oil_temperature_c.toFixed(1)}°C</td>
                <td>{item.telemetry.main_reservoir_pressure_mpa.toFixed(2)} MPa</td>
                <td>
                  {item.health.score.toFixed(1)} / {item.health.grade}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
