# Locomotive Digital Twin Prototype

This repository implements the `plan_v2.pdf` brief as a full-stack MVP for a KTZ locomotive digital twin. It includes:

- `backend/`: FastAPI API for telemetry ingest, Health Index scoring, alerts, history/export, auth, `/health`, `/metrics`, WebSocket streaming, and SSE fallback.
- `frontend/`: React + Vite dashboard with a health gauge, live charts, 3D locomotive twin, route map, alert feed, replay controls, and fleet overview.
- `simulator/`: Python telemetry generator with normal, degraded, and spike-mode runs.
- `docker-compose.yml`: single-command stack scaffold with backend, frontend, PostgreSQL, and Redis.
- `docs/`: reference materials:
  - `kz8a_specs.md` — verified KZ8A/KZ4AT/TE33A technical specs from research papers.
  - `kz8a_autopilot_notes.md` — observations from KZ8A autopilot cab demonstration.
  - `dataset.md` — public datasets for HI/RUL algorithm training (NASA C-MAPSS, PRONOSTIA, etc.).

## What is implemented

- Real-time ingest: `POST /telemetry`
- Authentication: `POST /auth/login`
- Live streams: `GET /stream?token=...` and `WS /ws?token=...`
- Health Index engine: formula-inspired score, grade bands `A-E`, top factor breakdown, and trend history
- Alerting: wheel slip, thermal, brake, reliability, and low-HI alerts persisted with the event stream
- History and export: `GET /telemetry`, `GET /alerts`, `GET /export?format=csv|json`
- Operations endpoints: `GET /health`, `GET /metrics`
- Frontend modules from the spec: health gauge, 3D twin, traction chart, subsystem monitoring, alert feed, route map (real Almaty↔Astana corridor), history/replay, fleet overview
- Route map: real KTZ railway segment Almaty-1 → Shu → Karaganda → Astana (~1,200 km) with station markers and traveled/remaining segments
- Simulator: GPS interpolation along real corridor waypoints with normal, degraded, and spike modes

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
docs/
frontend/
  src/
simulator/
```

## Local run

### Step 0: Seed the database (recommended for demo)

Pre-generates 600 synthetic events (3 locomotives × 200 events) into the SQLite database so the dashboard has data immediately — no need to wait for the simulator.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
python3 simulator/seed.py
# Optional: more events
python3 simulator/seed.py --events 500
```

Fleet seeded:
- `KZ8A-001` — Electric, nominal operation (Almaty → Astana)
- `KZ8A-002` — Electric, degraded operation (heat buildup + brake wear)
- `TE33A-009` — Diesel-electric, nominal (Astana → Almaty)

Data strategy: GPS positions are real KTZ railway corridor waypoints. All telemetry values are synthetic, per instructor guidance: *"Only the real railway network on maps can be real. Pick a segment and overlay synthesized data."*

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

The backend defaults to a local SQLite database under `backend/data/` for portability, while `backend/sql/init.sql` provides the PostgreSQL schema for production use.

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

### Simulator (live streaming)

Use `seed.py` (Step 0 above) for an instant populated database.
Use these commands to stream live synthetic telemetry to the running backend.

Demo credentials:

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

## Notes

- The backend persists to SQLite by default so the prototype can run without external services inside this workspace.
- The PostgreSQL and Redis services are included in Compose and the SQL schema is provided, but the runtime data path is intentionally lightweight for easier local demos.
- The frontend expects a browser environment for WebSocket/SSE, 3D rendering, and map tiles.
