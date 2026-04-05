import { startTransition, useEffect, useMemo, useState, type FormEvent } from "react";

import { fetchAlerts, fetchFleet, fetchHealth, fetchHistory, login } from "./api/client";
import { LocomotiveTwin3D } from "./components/LocomotiveTwin3D";
import { useTelemetryStream } from "./features/live/useTelemetryStream";
import type { AlertItem, EnrichedTelemetry, FleetCard, HealthSnapshot, TelemetryEvent } from "./types";

type Tone = "ok" | "warn" | "critical";
type ControlPanel = "diagnostics" | "replay" | "export" | null;

function defaultCredentials() {
  return { username: "admin", password: "admin123" };
}

function upperBand(value: number, normalMax: number, warnMax: number): Tone {
  if (value <= normalMax) return "ok";
  if (value <= warnMax) return "warn";
  return "critical";
}

function lowerBand(value: number, normalMin: number, warnMin: number): Tone {
  if (value >= normalMin) return "ok";
  if (value >= warnMin) return "warn";
  return "critical";
}

function rangeBand(value: number, normalMin: number, normalMax: number, warnMin: number, warnMax: number): Tone {
  if (value >= normalMin && value <= normalMax) return "ok";
  if (value >= warnMin && value <= warnMax) return "warn";
  return "critical";
}

function healthTone(grade: string | undefined): Tone {
  if (grade === "A" || grade === "B") return "ok";
  if (grade === "C") return "warn";
  return "critical";
}

function toneLabel(tone: Tone) {
  if (tone === "ok") return "Норма";
  if (tone === "warn") return "Предупреждение";
  return "Ошибка";
}

function gaugeColor(tone: Tone) {
  if (tone === "ok") return "#57d96b";
  if (tone === "warn") return "#ff9d2f";
  return "#ff4f52";
}

function formatClock(value: string | undefined) {
  if (!value) return "Нет данных";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function cadenceLabel(seconds: number) {
  if (seconds <= 1) return "ОБНОВЛЕНИЕ: 1 СЕК";
  return `ОБНОВЛЕНИЕ: ${seconds} СЕК`;
}

function downloadText(filename: string, body: string, mimeType: string) {
  const blob = new Blob([body], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function toCsv(history: EnrichedTelemetry[]) {
  const headers = [
    "timestamp",
    "locomotive_id",
    "locomotive_type",
    "speed_kmh",
    "tractive_effort_kn",
    "engine_oil_temperature_c",
    "coolant_temperature_c",
    "battery_voltage_v",
    "main_reservoir_pressure_mpa",
    "health_score",
    "health_grade",
    "alerts_count",
  ];
  const rows = history.map((item) => [
    item.telemetry.timestamp,
    item.telemetry.locomotive_id,
    item.telemetry.locomotive_type,
    item.telemetry.speed_kmh,
    item.telemetry.tractive_effort_kn,
    item.telemetry.engine_oil_temperature_c,
    item.telemetry.coolant_temperature_c,
    item.telemetry.battery_voltage_v,
    item.telemetry.main_reservoir_pressure_mpa,
    item.health.score,
    item.health.grade,
    item.alerts.length,
  ]);
  return [headers, ...rows]
    .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\n");
}

function buildSparkline(values: number[]) {
  const safeValues = values.length > 1 ? values : values.length === 1 ? [values[0], values[0]] : [0, 0];
  const width = 100;
  const height = 34;
  const min = Math.min(...safeValues);
  const max = Math.max(...safeValues);
  const span = Math.max(max - min, 1);
  return safeValues
    .map((value, index) => {
      const x = (index / (safeValues.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x},${y}`;
    })
    .join(" ");
}

function Sparkline({ values, tone }: { values: number[]; tone: Tone }) {
  return (
    <svg viewBox="0 0 100 34" className="sparkline">
      <polyline points={buildSparkline(values)} className={`sparkline-line tone-${tone}`} />
    </svg>
  );
}

function ReadoutCard({
  title,
  value,
  unit,
  tone,
  detail,
  trend,
}: {
  title: string;
  value: string;
  unit?: string;
  tone: Tone;
  detail: string;
  trend: number[];
}) {
  return (
    <article className={`console-card tone-${tone}`}>
      <div className="card-topline">
        <span>{title}</span>
        <b>{toneLabel(tone)}</b>
      </div>
      <div className="card-value">
        <strong>{value}</strong>
        {unit ? <span>{unit}</span> : null}
      </div>
      <Sparkline values={trend} tone={tone} />
      <small>{detail}</small>
    </article>
  );
}

function CircularDial({
  value,
  label,
  tone,
}: {
  value: number;
  label: string;
  tone: Tone;
}) {
  const angle = Math.max(0, Math.min(100, value));
  return (
    <div
      className="dial"
      style={{
        background: `conic-gradient(${gaugeColor(tone)} 0 ${angle * 2.7}deg, rgba(255,255,255,0.08) ${angle * 2.7}deg 270deg, transparent 270deg 360deg)`,
      }}
    >
      <div className="dial-inner">
        <strong>{value.toFixed(0)}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function MetricStatus({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: Tone;
}) {
  return (
    <div className="status-row">
      <span className={`status-dot tone-${tone}`} />
      <div>
        <strong>{label}</strong>
        <small>{value}</small>
      </div>
    </div>
  );
}

function mapSystemStatuses(telemetry: TelemetryEvent | null, health: HealthSnapshot | null) {
  if (!telemetry || !health) return [];
  return [
    {
      label: "Система тяги",
      value: `${telemetry.tractive_effort_kn.toFixed(0)} кН`,
      tone: upperBand(telemetry.tractive_effort_kn, 250, 400),
    },
    {
      label: "Тормозная система",
      value: `${telemetry.main_reservoir_pressure_mpa.toFixed(2)} МПа`,
      tone: lowerBand(telemetry.main_reservoir_pressure_mpa, 0.72, 0.6),
    },
    {
      label: "Электроснабжение",
      value: `${telemetry.battery_voltage_v.toFixed(0)} В`,
      tone: lowerBand(telemetry.battery_voltage_v, 100, 92),
    },
    {
      label: "Двигатель",
      value: `${telemetry.engine_oil_temperature_c.toFixed(0)} °C`,
      tone: upperBand(telemetry.engine_oil_temperature_c, 100, 118),
    },
    {
      label: "Индекс здоровья",
      value: `${health.score.toFixed(1)} / ${health.grade}`,
      tone: healthTone(health.grade),
    },
  ];
}

function routeRows(telemetry: TelemetryEvent | null) {
  if (!telemetry) return [];
  return [
    { label: "Текущая позиция", value: `${telemetry.gps_lat.toFixed(3)}, ${telemetry.gps_lon.toFixed(3)}` },
    { label: "Следующая станция", value: telemetry.locomotive_type === "KZ8A" ? "Алматы-2" : "Астана-Нурлы Жол" },
    { label: "Профиль пути", value: `${telemetry.track_gradient_permille.toFixed(1)}‰` },
    { label: "Лимит скорости", value: `${telemetry.speed_limit_kmh.toFixed(0)} км/ч` },
  ];
}

export default function App() {
  const [credentials, setCredentials] = useState(defaultCredentials());
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("digitalTwinToken"));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem("digitalTwinRole"));
  const [fleet, setFleet] = useState<FleetCard[]>([]);
  const [selectedLocomotiveId, setSelectedLocomotiveId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [history, setHistory] = useState<EnrichedTelemetry[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activePanel, setActivePanel] = useState<ControlPanel>(null);
  const [replayEventId, setReplayEventId] = useState<string | null>(null);

  const currentEvent = history[0] ?? null;
  const replayEvent = useMemo(
    () => history.find((item) => item.event_id === replayEventId) ?? null,
    [history, replayEventId],
  );
  const activeEvent = replayEvent ?? currentEvent;
  const telemetry = activeEvent?.telemetry ?? null;
  const displayHealth = replayEvent?.health ?? health;
  const liveAlerts = replayEvent?.alerts ?? alerts;
  const selectedFleet = useMemo(
    () => fleet.find((item) => item.locomotive_id === selectedLocomotiveId) ?? fleet[0] ?? null,
    [fleet, selectedLocomotiveId],
  );

  const { connected, transport } = useTelemetryStream(token, (event) => {
    startTransition(() => {
      setFleet((current) => {
        const existing = current.find((card) => card.locomotive_id === event.telemetry.locomotive_id);
        const nextCard: FleetCard = {
          locomotive_id: event.telemetry.locomotive_id,
          locomotive_type: event.telemetry.locomotive_type,
          last_seen: event.telemetry.timestamp,
          health_score: event.health.score,
          health_grade: event.health.grade,
          alert_count: event.alerts.length,
          speed_kmh: event.telemetry.speed_kmh,
          location: [event.telemetry.gps_lat, event.telemetry.gps_lon],
        };
        if (!existing) return [nextCard, ...current];
        return current.map((card) => (card.locomotive_id === nextCard.locomotive_id ? nextCard : card));
      });

      if (!selectedLocomotiveId || event.telemetry.locomotive_id === selectedLocomotiveId) {
        setSelectedLocomotiveId(event.telemetry.locomotive_id);
        setHealth(event.health);
        setAlerts((current) => [...event.alerts, ...current].slice(0, 18));
        setHistory((current) => [event, ...current.filter((item) => item.event_id !== event.event_id)].slice(0, 120));
      }
    });
  });

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    fetchFleet(token)
      .then((items) => {
        setFleet(items);
        if (!selectedLocomotiveId && items[0]) setSelectedLocomotiveId(items[0].locomotive_id);
      })
      .catch((fetchError) => setError(fetchError.message))
      .finally(() => setLoading(false));
  }, [token, selectedLocomotiveId]);

  useEffect(() => {
    if (!token || !selectedLocomotiveId) return;
    setReplayEventId(null);
    Promise.all([
      fetchHealth(token, selectedLocomotiveId),
      fetchHistory(token, selectedLocomotiveId),
      fetchAlerts(token, selectedLocomotiveId),
    ])
      .then(([healthResponse, historyResponse, alertsResponse]) => {
        setHealth(healthResponse);
        setHistory(historyResponse);
        setAlerts(alertsResponse);
      })
      .catch((fetchError) => setError(fetchError.message));
  }, [token, selectedLocomotiveId]);

  async function handleLoginSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await login(credentials.username, credentials.password);
      localStorage.setItem("digitalTwinToken", response.access_token);
      localStorage.setItem("digitalTwinRole", response.role);
      setToken(response.access_token);
      setRole(response.role);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("digitalTwinToken");
    localStorage.removeItem("digitalTwinRole");
    setToken(null);
    setRole(null);
    setFleet([]);
    setHealth(null);
    setHistory([]);
    setAlerts([]);
    setSelectedLocomotiveId(null);
  }

  const speedTone = telemetry ? upperBand(telemetry.speed_kmh / Math.max(telemetry.speed_limit_kmh, 1), 0.75, 1) : "ok";
  const effortTone = telemetry ? upperBand(telemetry.tractive_effort_kn, 250, 400) : "ok";
  const accelTone = telemetry ? upperBand(Math.abs(telemetry.acceleration_mps2), 1, 2) : "ok";
  const fuelTone = telemetry
    ? telemetry.locomotive_type === "TE33A"
      ? lowerBand(telemetry.fuel_level_pct ?? 0, 35, 20)
      : rangeBand(telemetry.catenary_voltage_kv ?? 0, 20, 28, 19, 28.5)
    : "ok";
  const batteryTone = telemetry ? lowerBand(telemetry.battery_voltage_v, 100, 92) : "ok";
  const powerTone = telemetry
    ? telemetry.locomotive_type === "KZ8A"
      ? upperBand(telemetry.electric_power_kw ?? 0, 5000, 7000)
      : upperBand(telemetry.fuel_consumption_lph ?? 0, 300, 600)
    : "ok";
  const reservoirTone = telemetry ? lowerBand(telemetry.main_reservoir_pressure_mpa, 0.72, 0.6) : "ok";
  const oilTone = telemetry ? upperBand(telemetry.engine_oil_temperature_c, 100, 118) : "ok";
  const coolantTone = telemetry ? upperBand(telemetry.coolant_temperature_c, 88, 102) : "ok";
  const vibrationTone = telemetry ? upperBand(telemetry.vibration_amplitude_mms, 12, 28) : "ok";
  const healthDialTone = displayHealth ? healthTone(displayHealth.grade) : "ok";

  const speedTrend = history.slice(0, 18).map((item) => item.telemetry.speed_kmh).reverse();
  const effortTrend = history.slice(0, 18).map((item) => item.telemetry.tractive_effort_kn).reverse();
  const accelTrend = history.slice(0, 18).map((item) => item.telemetry.acceleration_mps2).reverse();
  const voltageTrend = history
    .slice(0, 18)
    .map((item) => (item.telemetry.locomotive_type === "TE33A" ? item.telemetry.battery_voltage_v : item.telemetry.catenary_voltage_kv ?? 0))
    .reverse();
  const powerTrend = history
    .slice(0, 18)
    .map((item) => item.telemetry.electric_power_kw ?? item.telemetry.fuel_consumption_lph ?? 0)
    .reverse();
  const healthTrend = history.slice(0, 18).map((item) => item.health.score).reverse();

  const systemStatuses = mapSystemStatuses(telemetry, displayHealth);
  const cadenceSeconds =
    telemetry && typeof telemetry.metadata?.cadence_seconds === "number"
      ? telemetry.metadata.cadence_seconds
      : 15;
  const fallbackAlerts: AlertItem[] =
    displayHealth?.factors.slice(0, 3).map((factor, index) => ({
      alert_id: `fallback-${index}`,
      locomotive_id: selectedLocomotiveId ?? "",
      timestamp: telemetry?.timestamp ?? new Date().toISOString(),
      severity: healthDialTone === "critical" ? "critical" : "warning",
      code: factor.key,
      message: factor.label,
      status: "open",
      source: factor.category,
      details: {},
    })) ?? [];
  const displayAlerts = (liveAlerts.length ? liveAlerts : fallbackAlerts).slice(0, 5);
  const engineCards = telemetry
    ? [
        {
          title: telemetry.locomotive_type === "TE33A" ? "Дизельный блок" : "Трансформатор",
          value:
            telemetry.locomotive_type === "TE33A"
              ? `${telemetry.engine_oil_temperature_c.toFixed(0)} °C`
              : `${(telemetry.transformer_oil_temp_c ?? 0).toFixed(0)} °C`,
          note:
            telemetry.locomotive_type === "TE33A"
              ? `EGT ${telemetry.exhaust_gas_temperature_c.toFixed(0)} °C`
              : `Контактная сеть ${(telemetry.catenary_voltage_kv ?? 0).toFixed(1)} кВ`,
          tone: oilTone,
        },
        {
          title: "Тяговый контур",
          value: `${telemetry.traction_motor_current_a.toFixed(0)} A`,
          note: `Момент ${telemetry.traction_motor_torque_nm.toFixed(0)} Н·м`,
          tone: effortTone,
        },
        {
          title: "Охлаждение",
          value: `${telemetry.coolant_temperature_c.toFixed(0)} °C`,
          note: `Масло ${telemetry.engine_oil_pressure_mpa.toFixed(2)} МПа`,
          tone: coolantTone,
        },
        {
          title: "Пневматика",
          value: `${telemetry.main_reservoir_pressure_mpa.toFixed(2)} МПа`,
          note: `Торм. цилиндр ${telemetry.brake_cylinder_pressure_mpa.toFixed(2)} МПа`,
          tone: reservoirTone,
        },
      ]
    : [];
  const factorHighlights = (displayHealth?.factors ?? []).slice(0, 5);
  const replayEvents = history.slice(0, 14);

  function togglePanel(panel: Exclude<ControlPanel, null>) {
    setActivePanel((current) => (current === panel ? null : panel));
  }

  function clearReplay() {
    setReplayEventId(null);
  }

  function exportJson() {
    if (!history.length) return;
    downloadText(
      `${selectedLocomotiveId ?? "locomotive"}-telemetry.json`,
      JSON.stringify(history, null, 2),
      "application/json",
    );
  }

  function exportCsv() {
    if (!history.length) return;
    downloadText(`${selectedLocomotiveId ?? "locomotive"}-telemetry.csv`, toCsv(history), "text/csv;charset=utf-8");
  }

  if (!token) {
    return (
      <main className="login-screen">
        <section className="login-card">
          <p className="eyebrow">Цифровой двойник локомотива</p>
          <h1>Интерфейс машиниста для живой телеметрии и состояния систем.</h1>
          <form onSubmit={handleLoginSubmit} className="login-form">
            <label>
              Username
              <input
                value={credentials.username}
                onChange={(event) => setCredentials((current) => ({ ...current, username: event.target.value }))}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={credentials.password}
                onChange={(event) => setCredentials((current) => ({ ...current, password: event.target.value }))}
              />
            </label>
            <button type="submit" disabled={loading}>
              {loading ? "Подключение..." : "Запустить консоль"}
            </button>
          </form>
          <p className="helper-copy">Демо-логины: admin / admin123 и operator / demo123.</p>
          {error ? <div className="error-banner">{error}</div> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="console-app">
      <section className="console-frame">
        <header className="console-header">
          <div>
            <p className="eyebrow">Интерфейс машиниста</p>
            <h1>Цифровой двойник {selectedFleet?.locomotive_id ?? "KZ8A-0002"}</h1>
          </div>
          <div className="header-status">
            <span className={`status-pill tone-${healthDialTone}`}>
              {displayHealth ? `${displayHealth.score.toFixed(0)}/${displayHealth.grade}` : "—"}
            </span>
            <span className={`status-pill ${connected ? "tone-ok" : "tone-critical"}`}>
              {connected ? `${transport.toUpperCase()} LIVE` : "OFFLINE"}
            </span>
            <button className="metal-button" onClick={logout}>
              Выход
            </button>
          </div>
        </header>

        <div className="unit-switcher">
          {fleet.map((item) => (
            <button
              key={item.locomotive_id}
              className={`unit-tab ${item.locomotive_id === selectedLocomotiveId ? "active" : ""}`}
              onClick={() => setSelectedLocomotiveId(item.locomotive_id)}
            >
              <span>{item.locomotive_id}</span>
              <small>
                {item.health_score.toFixed(0)}/{item.health_grade}
              </small>
            </button>
          ))}
        </div>

        {error ? <div className="error-banner inline">{error}</div> : null}

        <section className="console-grid">
          <aside className="zone-column">
            <div className="zone-label">ZONE 1: ТЯГА И ДВИЖЕНИЕ</div>
            <ReadoutCard
              title="Скорость"
              value={telemetry ? telemetry.speed_kmh.toFixed(0) : "--"}
              unit="км/ч"
              tone={speedTone}
              detail={`Ограничение ${telemetry?.speed_limit_kmh.toFixed(0) ?? "--"} км/ч`}
              trend={speedTrend}
            />
            <ReadoutCard
              title="Тяговое усилие"
              value={telemetry ? telemetry.tractive_effort_kn.toFixed(0) : "--"}
              unit="кН"
              tone={effortTone}
              detail={`Боксование ${telemetry?.wheel_slip_ratio_pct.toFixed(1) ?? "--"}%`}
              trend={effortTrend}
            />
            <ReadoutCard
              title="Ускорение"
              value={telemetry ? telemetry.acceleration_mps2.toFixed(2) : "--"}
              unit="м/с²"
              tone={accelTone}
              detail={`Сцепление ${telemetry?.adhesion_coefficient.toFixed(2) ?? "--"} µ`}
              trend={accelTrend}
            />

            <div className="zone-label">ZONE 2: РЕСУРСЫ</div>
            <div className="resource-cluster">
              <div className={`resource-card tone-${fuelTone}`}>
                <span>{telemetry?.locomotive_type === "TE33A" ? "Уровень топлива" : "Напряжение цепей"}</span>
                <CircularDial
                  value={
                    telemetry
                      ? telemetry.locomotive_type === "TE33A"
                        ? telemetry.fuel_level_pct ?? 0
                        : ((telemetry.catenary_voltage_kv ?? 0) / 28.5) * 100
                      : 0
                  }
                  label={telemetry?.locomotive_type === "TE33A" ? `${(telemetry?.fuel_level_pct ?? 0).toFixed(0)}%` : `${(telemetry?.catenary_voltage_kv ?? 0).toFixed(1)} кВ`}
                  tone={fuelTone}
                />
              </div>
              <ReadoutCard
                title="Напряжение"
                value={telemetry ? telemetry.battery_voltage_v.toFixed(0) : "--"}
                unit="В"
                tone={batteryTone}
                detail={`Тяговая цепь ${telemetry?.traction_circuit_voltage_v.toFixed(0) ?? "--"} В`}
                trend={voltageTrend}
              />
              <ReadoutCard
                title={telemetry?.locomotive_type === "KZ8A" ? "Электроэнергия" : "Расход топлива"}
                value={
                  telemetry
                    ? telemetry.locomotive_type === "KZ8A"
                      ? (telemetry.electric_power_kw ?? 0).toFixed(1)
                      : (telemetry.fuel_consumption_lph ?? 0).toFixed(0)
                    : "--"
                }
                unit={telemetry?.locomotive_type === "KZ8A" ? "кВт" : "л/ч"}
                tone={powerTone}
                detail={`Вспом. нагрузка ${telemetry?.auxiliary_power_load_kw.toFixed(0) ?? "--"} кВт`}
                trend={powerTrend}
              />
            </div>
          </aside>

          <section className="center-column">
            <div className="zone-label">ZONE 3: ЦИФРОВОЙ ДВОЙНИК</div>
            <article className="twin-console">
              <div className="twin-grid" />
              <LocomotiveTwin3D health={displayHealth} className="twin-canvas" />
              <div className="twin-tags">
                <span className="twin-tag tone-ok">Тяговые двигатели</span>
                <span className={`twin-tag tone-${reservoirTone}`}>Тормозная система</span>
                <span className={`twin-tag tone-${oilTone}`}>Главный трансформатор</span>
                <span className={`twin-tag tone-${healthDialTone}`}>Система управления</span>
              </div>
              <div className="twin-footer">
                <div className="mini-label">Перед</div>
                <div className="mini-label">Зад</div>
                <div className="mini-label">Левая сторона</div>
                <div className="mini-label">Правая сторона</div>
              </div>
            </article>

            <article className="engine-bay">
              <div className="engine-bay-header">
                <div>
                  <p className="eyebrow">Engine Bay</p>
                  <h3>Подсистемы силовой установки</h3>
                </div>
                <span className={`status-pill tone-${healthDialTone}`}>{replayEvent ? "REPLAY" : "LIVE"}</span>
              </div>
              <div className="engine-grid">
                {engineCards.map((card) => (
                  <div key={card.title} className={`engine-card tone-${card.tone}`}>
                    <div className="engine-card-top">
                      <span>{card.title}</span>
                      <b>{toneLabel(card.tone)}</b>
                    </div>
                    <strong>{card.value}</strong>
                    <small>{card.note}</small>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <aside className="zone-column">
            <div className="zone-label">ZONE 4: ЗДОРОВЬЕ СИСТЕМЫ</div>
            <article className="health-console">
              <div className="health-top">
                <span>Индекс здоровья</span>
                <CircularDial
                  value={displayHealth?.score ?? 0}
                  label={displayHealth ? `${displayHealth.grade}/${displayHealth.band}` : "—"}
                  tone={healthDialTone}
                />
              </div>
              <Sparkline values={healthTrend} tone={healthDialTone} />
              <div className="status-stack">
                {systemStatuses.map((item) => (
                  <MetricStatus key={item.label} label={item.label} value={item.value} tone={item.tone} />
                ))}
              </div>
            </article>

            <div className="zone-label">ZONE 5: КАРТА ПУТИ И АЛЕРТЫ</div>
            <article className="route-console">
              <div className="route-rail">
                <div className="route-line" />
                <div className="route-marker current" />
                <div className="route-marker next" />
              </div>
              <div className="route-meta">
                {routeRows(telemetry).map((row) => (
                  <div key={row.label} className="route-row">
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))}
              </div>
              <div className="alert-log">
                {displayAlerts.map((alert) => (
                  <div key={alert.alert_id} className={`alert-row tone-${alert.severity === "critical" ? "critical" : "warn"}`}>
                    <span>{formatClock(alert.timestamp)}</span>
                    <strong>{alert.message}</strong>
                  </div>
                ))}
              </div>
            </article>
          </aside>
        </section>

        <footer className="console-footer">
          <div className="legend-group">
            <span className="legend-item tone-ok">OK</span>
            <span className="legend-item tone-warn">ПРЕДУПРЕЖДЕНИЕ</span>
            <span className="legend-item tone-critical">ОШИБКА</span>
            <span className="legend-item tone-ok">{cadenceLabel(cadenceSeconds)}</span>
          </div>
          <div className="console-actions">
            <button className={`metal-button ${activePanel === "diagnostics" ? "active" : ""}`} onClick={() => togglePanel("diagnostics")}>
              Диагностика
            </button>
            <button className={`metal-button ${activePanel === "replay" ? "active" : ""}`} onClick={() => togglePanel("replay")}>
              Реплей
            </button>
            <button className={`metal-button ${activePanel === "export" ? "active" : ""}`} onClick={() => togglePanel("export")}>
              Экспорт
            </button>
            <div className="updated-at">Последнее обновление: {formatClock(telemetry?.timestamp)}</div>
          </div>
        </footer>

        {activePanel ? (
          <section className="control-drawer">
            <div className="drawer-header">
              <div>
                <p className="eyebrow">Operator tools</p>
                <h3>
                  {activePanel === "diagnostics" ? "Диагностика и факторы риска" : activePanel === "replay" ? "Реплей телеметрии" : "Экспорт телеметрии"}
                </h3>
              </div>
              <button className="metal-button compact" onClick={() => setActivePanel(null)}>
                Закрыть
              </button>
            </div>

            {activePanel === "diagnostics" ? (
              <div className="drawer-grid diagnostics-grid">
                <div className="drawer-card">
                  <h4>Ключевые двигательные метрики</h4>
                  <div className="diag-matrix">
                    <div className={`diag-chip tone-${oilTone}`}>
                      <span>Масло</span>
                      <strong>{telemetry?.engine_oil_temperature_c.toFixed(0) ?? "--"} °C</strong>
                    </div>
                    <div className={`diag-chip tone-${coolantTone}`}>
                      <span>Охлаждение</span>
                      <strong>{telemetry?.coolant_temperature_c.toFixed(0) ?? "--"} °C</strong>
                    </div>
                    <div className={`diag-chip tone-${effortTone}`}>
                      <span>Тяга</span>
                      <strong>{telemetry?.traction_motor_current_a.toFixed(0) ?? "--"} A</strong>
                    </div>
                    <div className={`diag-chip tone-${vibrationTone}`}>
                      <span>Вибрация</span>
                      <strong>{telemetry?.vibration_amplitude_mms.toFixed(1) ?? "--"} мм/с</strong>
                    </div>
                    <div className={`diag-chip tone-${batteryTone}`}>
                      <span>Аккумулятор</span>
                      <strong>{telemetry?.battery_voltage_v.toFixed(0) ?? "--"} В</strong>
                    </div>
                    <div className={`diag-chip tone-${reservoirTone}`}>
                      <span>Пневматика</span>
                      <strong>{telemetry?.main_reservoir_pressure_mpa.toFixed(2) ?? "--"} МПа</strong>
                    </div>
                  </div>
                </div>

                <div className="drawer-card">
                  <h4>Топ-факторы Health Index</h4>
                  <div className="factor-list">
                    {factorHighlights.length ? (
                      factorHighlights.map((factor) => (
                        <div key={factor.key} className="factor-row">
                          <div>
                            <strong>{factor.label}</strong>
                            <small>{factor.detail}</small>
                          </div>
                          <div className="factor-meter">
                            <span style={{ width: `${Math.min(factor.penalty, 100)}%` }} />
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="empty-copy">Пока нет факторов риска для выбранного события.</p>
                    )}
                  </div>
                </div>

                <div className="drawer-card wide">
                  <h4>Сводка по силовой цепочке</h4>
                  <div className="diag-lines">
                    <div className="diag-line">
                      <span>Турбокомпрессор</span>
                      <strong>{telemetry?.turbocharger_rpm.toFixed(0) ?? "--"} rpm</strong>
                    </div>
                    <div className="diag-line">
                      <span>Exhaust Gas</span>
                      <strong>{telemetry?.exhaust_gas_temperature_c.toFixed(0) ?? "--"} °C</strong>
                    </div>
                    <div className="diag-line">
                      <span>Тяговое напряжение</span>
                      <strong>{telemetry?.traction_circuit_voltage_v?.toFixed(0) ?? "--"} В</strong>
                    </div>
                    <div className="diag-line">
                      <span>Контактная сеть / топливо</span>
                      <strong>
                        {telemetry?.locomotive_type === "KZ8A"
                          ? `${(telemetry?.catenary_voltage_kv ?? 0).toFixed(1)} кВ`
                          : `${(telemetry?.fuel_level_pct ?? 0).toFixed(0)}%`}
                      </strong>
                    </div>
                    <div className="diag-line">
                      <span>Наработка после ТО</span>
                      <strong>{telemetry?.operating_hours_since_last_service_h.toFixed(0) ?? "--"} ч</strong>
                    </div>
                    <div className="diag-line">
                      <span>Availability / MTBF</span>
                      <strong>
                        {telemetry?.locomotive_availability_pct.toFixed(0) ?? "--"}% / {telemetry?.mtbf_h.toFixed(0) ?? "--"} ч
                      </strong>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {activePanel === "replay" ? (
              <div className="drawer-grid replay-grid">
                <div className="drawer-card wide">
                  <div className="replay-toolbar">
                    <div>
                      <h4>Лента последних событий</h4>
                      <p className="helper-copy">Выберите точку, чтобы заморозить экран на выбранном состоянии локомотива.</p>
                    </div>
                    <button className="metal-button compact" onClick={clearReplay}>
                      Вернуться в LIVE
                    </button>
                  </div>
                  <div className="timeline-list">
                    {replayEvents.map((item) => (
                      <button
                        key={item.event_id}
                        className={`timeline-item ${item.event_id === replayEventId ? "active" : ""}`}
                        onClick={() => setReplayEventId(item.event_id)}
                      >
                        <span>{formatClock(item.telemetry.timestamp)}</span>
                        <strong>{item.health.score.toFixed(1)}/{item.health.grade}</strong>
                        <small>
                          {item.telemetry.speed_kmh.toFixed(0)} км/ч, {item.alerts.length} alerts
                        </small>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {activePanel === "export" ? (
              <div className="drawer-grid export-grid">
                <div className="drawer-card">
                  <h4>Экспорт состояния</h4>
                  <p className="helper-copy">Скачать последние события выбранного локомотива для отчета, демо или ручного анализа.</p>
                  <div className="export-actions">
                    <button className="metal-button" onClick={exportJson}>
                      Скачать JSON
                    </button>
                    <button className="metal-button" onClick={exportCsv}>
                      Скачать CSV
                    </button>
                  </div>
                </div>
                <div className="drawer-card">
                  <h4>Что входит</h4>
                  <div className="diag-lines">
                    <div className="diag-line">
                      <span>Локомотив</span>
                      <strong>{selectedLocomotiveId ?? "—"}</strong>
                    </div>
                    <div className="diag-line">
                      <span>Событий в буфере</span>
                      <strong>{history.length}</strong>
                    </div>
                    <div className="diag-line">
                      <span>Последний Health Index</span>
                      <strong>{displayHealth ? `${displayHealth.score.toFixed(1)} / ${displayHealth.grade}` : "—"}</strong>
                    </div>
                    <div className="diag-line">
                      <span>Режим</span>
                      <strong>{replayEvent ? "Replay snapshot" : "Live stream"}</strong>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}
      </section>
    </main>
  );
}
