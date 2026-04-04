import type { AlertItem } from "../types";

interface AlertFeedProps {
  alerts: AlertItem[];
}

export function AlertFeed({ alerts }: AlertFeedProps) {
  return (
    <section className="panel alert-panel">
      <div className="panel-header">
        <p>Alert Feed</p>
        <span className="muted">{alerts.length} active</span>
      </div>
      <div className="alert-list">
        {alerts.length === 0 ? (
          <div className="empty-state">No active alerts. System is tracking nominal operation.</div>
        ) : (
          alerts.map((alert) => (
            <article key={alert.alert_id} className={`alert-card severity-${alert.severity}`}>
              <div className="alert-topline">
                <strong>{alert.message}</strong>
                <span>{new Date(alert.timestamp).toLocaleTimeString()}</span>
              </div>
              <div className="alert-meta">
                <span>{alert.code}</span>
                <span>{alert.source}</span>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
