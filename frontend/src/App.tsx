import { useEffect, useMemo, useState, startTransition, useDeferredValue, type FormEvent } from "react";

import { fetchAlerts, fetchFleet, fetchHealth, fetchHistory, login } from "./api/client";
import { AlertFeed } from "./components/AlertFeed";
import { FleetOverview } from "./components/FleetOverview";
import { HealthGauge } from "./components/HealthGauge";
import { HistoryTable } from "./components/HistoryTable";
import { LocomotiveTwin3D } from "./components/LocomotiveTwin3D";
import { ReplayPanel } from "./components/ReplayPanel";
import { RouteMap } from "./components/RouteMap";
import { TelemetryChart } from "./components/TelemetryChart";
import { useTelemetryStream } from "./features/live/useTelemetryStream";
import type { AlertItem, EnrichedTelemetry, FleetCard, HealthSnapshot } from "./types";

function defaultCredentials() {
  return { username: "admin", password: "admin123" };
}

function translateRole(role: string | null) {
  if (role === "admin") return "администратор";
  if (role === "operator") return "оператор";
  return role ?? "оператор";
}

function translateTransport(transport: "idle" | "websocket" | "sse", connected: boolean) {
  if (!connected) {
    return "не в сети";
  }
  if (transport === "websocket") {
    return "WS онлайн";
  }
  if (transport === "sse") {
    return "SSE онлайн";
  }
  return "онлайн";
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
  const [replayIndex, setReplayIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  const liveItem = history[0] ?? null;
  const deferredLiveItem = useDeferredValue(liveItem);

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
        if (!existing) {
          return [nextCard, ...current];
        }
        return current.map((card) => (card.locomotive_id === nextCard.locomotive_id ? nextCard : card));
      });

      if (!selectedLocomotiveId || event.telemetry.locomotive_id === selectedLocomotiveId) {
        setSelectedLocomotiveId(event.telemetry.locomotive_id);
        setHealth(event.health);
        setAlerts((current) => [...event.alerts, ...current].slice(0, 25));
        setHistory((current) => [event, ...current.filter((item) => item.event_id !== event.event_id)].slice(0, 120));
      }
    });
  });

  useEffect(() => {
    if (!token) {
      return;
    }

    setLoading(true);
    fetchFleet(token)
      .then((items) => {
        setFleet(items);
        if (!selectedLocomotiveId && items[0]) {
          setSelectedLocomotiveId(items[0].locomotive_id);
        }
      })
      .catch((fetchError) => setError(fetchError.message))
      .finally(() => setLoading(false));
  }, [token, selectedLocomotiveId]);

  useEffect(() => {
    if (!token || !selectedLocomotiveId) {
      return;
    }

    Promise.all([
      fetchHealth(token, selectedLocomotiveId),
      fetchHistory(token, selectedLocomotiveId),
      fetchAlerts(token, selectedLocomotiveId),
    ])
      .then(([healthResponse, historyResponse, alertsResponse]) => {
        setHealth(healthResponse);
        setHistory(historyResponse);
        setAlerts(alertsResponse);
        setReplayIndex(0);
      })
      .catch((fetchError) => setError(fetchError.message));
  }, [token, selectedLocomotiveId]);

  useEffect(() => {
    if (!playing || history.length === 0) {
      return;
    }
    const handle = window.setInterval(() => {
      setReplayIndex((current) => {
        if (current >= history.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 850);
    return () => window.clearInterval(handle);
  }, [playing, history.length]);

  const replayItem = history[replayIndex] ?? deferredLiveItem;
  const metrics = useMemo(() => {
    if (!replayItem) {
      return [];
    }
    const tel = replayItem.telemetry;
    // Fuel efficiency — plan §8.3
    let fuelEfficiency = "Н/Д";
    if (tel.locomotive_type === "TE33A" && tel.fuel_consumption_lph && tel.fuel_consumption_lph > 0 && tel.speed_kmh > 0) {
      fuelEfficiency = `${(tel.speed_kmh / tel.fuel_consumption_lph).toFixed(2)} км/л`;
    } else if (tel.locomotive_type === "KZ8A" && tel.electric_power_kw && tel.electric_power_kw > 0 && tel.speed_kmh > 0) {
      fuelEfficiency = `${(tel.electric_power_kw / tel.speed_kmh).toFixed(1)} кВт·ч/км`;
    }
    return [
      { label: "Скорость", value: `${tel.speed_kmh.toFixed(1)} км/ч` },
      { label: "Тяговое усилие", value: `${tel.tractive_effort_kn.toFixed(0)} кН` },
      { label: "Температура масла", value: `${tel.engine_oil_temperature_c.toFixed(1)} °C` },
      { label: "Температура ОЖ", value: `${tel.coolant_temperature_c.toFixed(1)} °C` },
      { label: "Тормозное давление", value: `${tel.main_reservoir_pressure_mpa.toFixed(2)} МПа` },
      {
        label: tel.locomotive_type === "TE33A" ? "Уровень топлива" : "Напряжение контактной сети",
        value:
          tel.locomotive_type === "TE33A"
            ? `${(tel.fuel_level_pct ?? 0).toFixed(1)} %`
            : `${(tel.catenary_voltage_kv ?? 0).toFixed(1)} кВ`,
      },
      // §8.3 Operational KPIs
      { label: "Готовность", value: `${tel.locomotive_availability_pct.toFixed(1)} %` },
      { label: "MTBF", value: `${tel.mtbf_h.toFixed(0)} ч` },
      { label: "MTTR", value: `${tel.mttr_h.toFixed(1)} ч` },
      { label: "Ресурс тормозных колодок", value: `${tel.brake_pad_wear_pct_remaining.toFixed(1)} %` },
      { label: tel.locomotive_type === "TE33A" ? "Топливная эффективность" : "Энергоэффективность", value: fuelEfficiency },
      { label: "Вибрация", value: `${tel.vibration_amplitude_mms.toFixed(1)} мм/с` },
    ];
  }, [replayItem]);

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
      setError(loginError instanceof Error ? loginError.message : "Не удалось выполнить вход");
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

  if (!token) {
    return (
      <main className="login-screen">
        <section className="login-card">
          <p className="eyebrow">Цифровой двойник локомотива КТЖ</p>
          <h1>Телеметрия в реальном времени, оценка технического состояния и контроль по маршруту.</h1>
          <form onSubmit={handleLoginSubmit} className="login-form">
            <label>
              Логин
              <input
                value={credentials.username}
                onChange={(event) => setCredentials((current) => ({ ...current, username: event.target.value }))}
              />
            </label>
            <label>
              Пароль
              <input
                type="password"
                value={credentials.password}
                onChange={(event) => setCredentials((current) => ({ ...current, password: event.target.value }))}
              />
            </label>
            <button type="submit" disabled={loading}>
              {loading ? "Вход..." : "Открыть панель"}
            </button>
          </form>
          <p className="helper-copy">Демо-аккаунты: admin / admin123 и operator / demo123.</p>
          {error ? <div className="error-banner">{error}</div> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="hero-header">
        <div>
          <p className="eyebrow">Прототип по Operational Plan v2</p>
          <h1>Центр управления цифровым двойником локомотива</h1>
          <p className="hero-copy">
            Потоковая телеметрия, расчёт индекса состояния, маршрутный контекст и воспроизведение истории для локомотивов KZ8A и TE33A.
          </p>
        </div>
        <div className="hero-actions">
          <div className="status-badge">{translateRole(role)}</div>
          <div className={`status-badge ${connected ? "status-live" : "status-offline"}`}>
            {translateTransport(transport, connected)}
          </div>
          <button className="ghost-button" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <FleetOverview
        fleet={fleet}
        selectedLocomotiveId={selectedLocomotiveId}
        onSelect={setSelectedLocomotiveId}
      />

      <section className="dashboard-grid">
        <HealthGauge health={health} />
        <LocomotiveTwin3D health={health} />
        <AlertFeed alerts={alerts} />
        <TelemetryChart title="Тяга и движение" items={history} />
        <RouteMap
          position={
            replayItem
              ? [replayItem.telemetry.gps_lat, replayItem.telemetry.gps_lon]
              : selectedLocomotiveId
                ? fleet.find((item) => item.locomotive_id === selectedLocomotiveId)?.location ?? null
                : null
          }
          speedLimit={replayItem?.telemetry.speed_limit_kmh ?? 120}
          gradient={replayItem?.telemetry.track_gradient_permille ?? 0}
        />
        <section className="panel metrics-panel">
          <div className="panel-header">
            <p>Мониторинг подсистем</p>
            <span className="muted">{loading ? "Обновление..." : "Текущий срез"}</span>
          </div>
          <div className="metric-card-grid">
            {metrics.map((metric) => (
              <article key={metric.label} className="metric-card">
                <label>{metric.label}</label>
                <strong>{metric.value}</strong>
              </article>
            ))}
          </div>
        </section>
        <ReplayPanel
          history={history}
          replayIndex={replayIndex}
          onReplayIndexChange={setReplayIndex}
          onPlay={() => setPlaying((current) => !current)}
          playing={playing}
        />
        <HistoryTable history={history} />
      </section>
    </main>
  );
}
