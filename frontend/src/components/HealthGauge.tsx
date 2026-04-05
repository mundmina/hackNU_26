import type { HealthSnapshot } from "../types";

interface HealthGaugeProps {
  health: HealthSnapshot | null;
}

const HEALTH_BANDS: Record<string, string> = {
  Normal: "Норма",
  Advisory: "Замечание",
  Caution: "Внимание",
  Warning: "Предупреждение",
  Critical: "Критично",
};

const FACTOR_LABELS: Record<string, string> = {
  speed: "Использование скорости",
  acceleration: "Ускорение",
  tractive_effort: "Тяговое усилие",
  resource_burn: "Расход ресурса",
  track_gradient: "Уклон пути",
  wheel_slip: "Проскальзывание колёс",
  adhesion: "Коэффициент сцепления",
  oil_temp: "Температура моторного масла",
  coolant_temp: "Температура охлаждающей жидкости",
  oil_pressure: "Давление масла",
  egt: "Температура выхлопных газов",
  motor_temp: "Температура обмотки тягового двигателя",
  transformer_temp: "Температура масла трансформатора",
  vibration: "Вибрация колёсной пары",
  vertical_dynamics: "Коэффициент вертикальной динамики",
  frame_force: "Рамная сила",
  turbocharger_rpm: "Обороты турбокомпрессора",
  ambient_temp: "Температура окружающей среды",
  catenary_voltage: "Напряжение контактной сети",
  error_codes: "Активные коды ошибок",
  error_frequency: "Частота кодов ошибок",
  service_hours: "Часы после ТО",
  mtbf: "MTBF",
  mttr: "MTTR",
  availability: "Готовность локомотива",
  overhaul_distance: "Пробег после капремонта",
  reservoir_pressure: "Давление в главном резервуаре",
  brake_pad_remaining: "Остаточный ресурс колодок",
  solenoid_signal: "Остаточный сигнал соленоида",
  battery_voltage: "Напряжение батареи",
  compressor_pressure: "Давление компрессора",
};

function scoreColor(score: number) {
  if (score >= 85) return "#3ccf91";
  if (score >= 70) return "#f2b94b";
  if (score >= 50) return "#ff8a4c";
  if (score >= 30) return "#ff5b6e";
  return "#d7263d";
}

export function HealthGauge({ health }: HealthGaugeProps) {
  const score = health?.score ?? 0;
  const stroke = scoreColor(score);
  const radius = 88;
  const circumference = Math.PI * radius;
  const progress = circumference * (score / 100);

  return (
    <section className="panel gauge-panel">
      <div className="panel-header">
        <p>Индекс состояния</p>
        <span className={`grade grade-${health?.grade?.toLowerCase() ?? "e"}`}>{health?.grade ?? "E"}</span>
      </div>
      <div className="gauge-shell">
        <svg viewBox="0 0 220 140" className="gauge-svg">
          <path d="M22 118 A88 88 0 0 1 198 118" className="gauge-track" />
          <path
            d="M22 118 A88 88 0 0 1 198 118"
            className="gauge-progress"
            pathLength={circumference}
            stroke={stroke}
            strokeDasharray={`${progress} ${circumference}`}
          />
        </svg>
        <div className="gauge-readout">
          <strong>{score.toFixed(1)}</strong>
          <span>{health?.band ? HEALTH_BANDS[health.band] ?? health.band : "Ожидание телеметрии"}</span>
        </div>
      </div>
      <div className="modifier-grid">
        <div>
          <label>Нагрузка</label>
          <span>{health?.load_modifier.toFixed(3) ?? "0.000"}</span>
        </div>
        <div>
          <label>Состояние</label>
          <span>{health?.health_modifier.toFixed(3) ?? "0.000"}</span>
        </div>
        <div>
          <label>Надёжность</label>
          <span>{health?.reliability_modifier.toFixed(3) ?? "0.000"}</span>
        </div>
      </div>
      <div className="factor-list">
        {(health?.factors ?? []).slice(0, 4).map((factor) => (
          <div key={factor.key} className="factor-pill">
            <strong>{FACTOR_LABELS[factor.key] ?? factor.label}</strong>
            <span>-{factor.penalty.toFixed(1)} б.</span>
          </div>
        ))}
      </div>
    </section>
  );
}
