CREATE TABLE IF NOT EXISTS locomotives (
    locomotive_id TEXT PRIMARY KEY,
    locomotive_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id TEXT PRIMARY KEY,
    locomotive_id TEXT NOT NULL,
    locomotive_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    health_score DOUBLE PRECISION NOT NULL,
    health_grade TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    health_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_locomotive_time
    ON telemetry_events (locomotive_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    locomotive_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    details_json JSONB NOT NULL,
    recommendation TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_alerts_locomotive_time
    ON alerts (locomotive_id, timestamp DESC);
