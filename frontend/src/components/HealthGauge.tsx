import type { HealthSnapshot } from "../types";

interface HealthGaugeProps {
  health: HealthSnapshot | null;
}

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
        <p>Health Index</p>
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
          <span>{health?.band ?? "Waiting for telemetry"}</span>
        </div>
      </div>
      <div className="modifier-grid">
        <div>
          <label>Load</label>
          <span>{health?.load_modifier.toFixed(3) ?? "0.000"}</span>
        </div>
        <div>
          <label>Health</label>
          <span>{health?.health_modifier.toFixed(3) ?? "0.000"}</span>
        </div>
        <div>
          <label>Reliability</label>
          <span>{health?.reliability_modifier.toFixed(3) ?? "0.000"}</span>
        </div>
      </div>
      <div className="factor-list">
        {(health?.factors ?? []).slice(0, 4).map((factor) => (
          <div key={factor.key} className="factor-pill">
            <strong>{factor.label}</strong>
            <span>-{factor.penalty.toFixed(1)} pts</span>
          </div>
        ))}
      </div>
    </section>
  );
}
