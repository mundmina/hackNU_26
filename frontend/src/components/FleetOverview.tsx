import type { FleetCard } from "../types";

interface FleetOverviewProps {
  fleet: FleetCard[];
  selectedLocomotiveId: string | null;
  onSelect: (locomotiveId: string) => void;
}

export function FleetOverview({ fleet, selectedLocomotiveId, onSelect }: FleetOverviewProps) {
  return (
    <section className="panel fleet-panel">
      <div className="panel-header">
        <p>Обзор парка</p>
        <span className="muted">{fleet.length} локомотивов</span>
      </div>
      <div className="fleet-grid">
        {fleet.map((card) => (
          <button
            key={card.locomotive_id}
            className={`fleet-card ${selectedLocomotiveId === card.locomotive_id ? "selected" : ""}`}
            onClick={() => onSelect(card.locomotive_id)}
          >
            <strong>{card.locomotive_id}</strong>
            <span>{card.locomotive_type}</span>
            <div className="fleet-score">
              <span>{card.health_score.toFixed(1)}</span>
              <small>{card.health_grade}</small>
            </div>
            <small>{card.alert_count} тревог</small>
          </button>
        ))}
      </div>
    </section>
  );
}
