# Locomotive Digital Twin Prototype

This repository implements the locomotive digital twin brief as a full-stack MVP for a KTZ operator console. The current version also applies the threshold tables from the uploaded `metrics.pdf`, adds a machinist-style cockpit UI, and can auto-publish demo telemetry from the backend every 15 seconds by default so the frontend can act as a live display only.

- `backend/`: FastAPI API for telemetry ingest, Health Index scoring, alerts, history/export, auth, `/health`, `/metrics`, WebSocket streaming, and SSE fallback.
- `frontend/`: React + Vite operator console with a machinist-inspired metallic cockpit layout, a 3D locomotive twin, subsystem health, route/status panels, and live alert readouts.
- `simulator/`: Python telemetry generator with normal, degraded, and spike-mode runs.
- `docker-compose.yml`: single-command stack scaffold with backend, frontend, PostgreSQL, and Redis.

## What is implemented

- Real-time ingest: `POST /telemetry`
- Authentication: `POST /auth/login`
- Live streams: `GET /stream?token=...` and `WS /ws?token=...`
- Backend autopilot: emits demo telemetry every 15 seconds by default so the frontend can simply listen and render
- Health Index engine: score bands `A-E`, top factor breakdown, trend history, and PDF-driven thresholds for traction, voltage, thermal, brake, vibration, service, and reliability metrics
- Alerting: wheel slip, thermal, voltage, brake, vibration, reliability, and low-HI alerts persisted with the event stream
- History and export: `GET /telemetry`, `GET /alerts`, `GET /export?format=csv|json`
- BI/reporting layer: `GET /analytics/kpis`, `/analytics/trends`, `/analytics/breakdown`, `/analytics/factors`, `/analytics/alerts/trends`, `/analytics/alerts/breakdown`, `/analytics/events`
- Operations endpoints: `GET /health`, `GET /metrics`
- Frontend modules from the spec: health gauge, 3D twin, traction chart, subsystem monitoring, alert feed, route map, history/replay, fleet overview
- Looker Studio integration scaffold: Apps Script community connector in `looker_studio_connector/` and dashboard design guide in `docs/looker-studio-dashboard.md`

## Repo layout

```text
backend/
  app/
    api/
    core/
    schemas/
    services/
    storage/
  sql/
  tests/
frontend/
  src/
simulator/
looker_studio_connector/
docs/
```

## Local run

### Backend

1. Create a virtual environment and install dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start the API:

```bash
uvicorn app.main:app --reload
```

The backend defaults to a local SQLite database under `backend/data/` for portability in this sandboxed workspace, while `backend/sql/init.sql` provides the PostgreSQL schema requested by the plan.

By default the backend also starts a demo autopilot and emits fresh telemetry every 15 seconds. You can tune or disable that with:

```bash
ENABLE_DEMO_AUTOPILOT=true
AUTOPILOT_INTERVAL_SECONDS=15
```

### Frontend

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Run Vite:

```bash
npm run dev
```

Set `VITE_API_BASE_URL` if your backend is not at `http://127.0.0.1:8000`.

### Simulator

After logging in credentials are available by default:

- `admin / admin123`
- `operator / demo123`

Run a nominal KZ8A stream:

```bash
python3 simulator/simulate.py --locomotive-id KZ8A-001 --locomotive-type KZ8A
```

Run a degraded diesel-electric stress scenario:

```bash
python3 simulator/simulate.py --locomotive-id TE33A-009 --locomotive-type TE33A --degraded
```

Run a burst demo:

```bash
python3 simulator/simulate.py --locomotive-id KZ8A-001 --spike-mode
```

You can use the simulator in addition to the backend autopilot, but it is no longer required just to make the frontend look live.

## Docker Compose

When Docker is available:

```bash
docker-compose up --build
```

The compose file provisions:

- `backend` on `:8000`
- `frontend` on `:5173`
- `postgres` on `:5432`
- `redis` on `:6379`

## Verification

- Backend syntax can be checked with `python3 -m compileall backend simulator`
- Health Index tests can be run with `PYTHONPATH=backend python3 -m unittest backend/tests/test_health_engine.py`
- Analytics/reporting tests can be run with `PYTHONPATH=backend python3 -m unittest backend/tests/test_analytics_reporting.py`

## Looker Studio

This repo now includes a reporting-oriented backend layer plus a Google Apps Script community connector scaffold:

- Connector code: `looker_studio_connector/Code.js`
- Apps Script manifest: `looker_studio_connector/appsscript.json`
- Dashboard setup guide: `docs/looker-studio-dashboard.md`

The recommended path is:

1. Run the backend and simulator.
2. Deploy the Apps Script connector.
3. Connect Looker Studio to one of the analytics datasets.
4. Build scorecards, trends, breakdowns, and alert analysis pages using the guide.

## Notes

- The backend persists to SQLite by default so the prototype can run without external services inside this workspace.
- The PostgreSQL and Redis services are included in Compose and the SQL schema is provided, but the runtime data path is intentionally lightweight for easier local demos.
- The frontend expects a browser environment for WebSocket/SSE, 3D rendering, and map tiles.
