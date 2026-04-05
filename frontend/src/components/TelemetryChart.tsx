import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EnrichedTelemetry } from "../types";

interface TelemetryChartProps {
  title: string;
  items: EnrichedTelemetry[];
}

const CHART_LABELS: Record<string, string> = {
  speed: "Скорость",
  effort: "Тяговое усилие",
  oil: "Температура масла",
  pressure: "Давление",
  health: "Индекс состояния",
};

export function TelemetryChart({ title, items }: TelemetryChartProps) {
  const data = items
    .slice()
    .reverse()
    .map((item) => ({
      time: new Date(item.telemetry.timestamp).toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      speed: item.telemetry.speed_kmh,
      effort: item.telemetry.tractive_effort_kn,
      oil: item.telemetry.engine_oil_temperature_c,
      pressure: item.telemetry.main_reservoir_pressure_mpa * 100,
      health: item.health.score,
    }));

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <p>{title}</p>
        <span className="muted">{items.length} точек</span>
      </div>
      <div className="chart-shell">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="4 4" stroke="rgba(255,255,255,0.08)" />
            <XAxis dataKey="time" stroke="#bcc4d6" minTickGap={24} />
            <YAxis stroke="#bcc4d6" />
            <Tooltip formatter={(value, name) => [value, CHART_LABELS[String(name)] ?? String(name)]} />
            <Legend formatter={(value) => CHART_LABELS[String(value)] ?? String(value)} />
            <Line type="monotone" dataKey="speed" stroke="#58c5ff" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="effort" stroke="#f2b94b" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="oil" stroke="#ff6a67" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="health" stroke="#3ccf91" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
