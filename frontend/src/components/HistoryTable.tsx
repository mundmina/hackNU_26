import type { EnrichedTelemetry } from "../types";

interface HistoryTableProps {
  history: EnrichedTelemetry[];
}

export function HistoryTable({ history }: HistoryTableProps) {
  return (
    <section className="panel history-panel">
      <div className="panel-header">
        <p>История телеметрии</p>
        <span className="muted">Последние сохранённые события</span>
      </div>
      <div className="history-table">
        <table>
          <thead>
            <tr>
              <th>Время</th>
              <th>Скорость</th>
              <th>Бокс.</th>
              <th>Масло</th>
              <th>Тормоза</th>
              <th>HI</th>
            </tr>
          </thead>
          <tbody>
            {history.slice(0, 12).map((item) => (
              <tr key={item.event_id}>
                <td>{new Date(item.telemetry.timestamp).toLocaleTimeString("ru-RU")}</td>
                <td>{item.telemetry.speed_kmh.toFixed(1)}</td>
                <td>{item.telemetry.wheel_slip_ratio_pct.toFixed(2)}%</td>
                <td>{item.telemetry.engine_oil_temperature_c.toFixed(1)}°C</td>
                <td>{item.telemetry.main_reservoir_pressure_mpa.toFixed(2)} МПа</td>
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
