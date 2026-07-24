# Changelog

All notable changes to PRISM are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Phase 0] — 2026-07-23

### Security
- **F2** — Secrets management: all credentials now loaded from environment variables
  via `config.py` + `python-dotenv`. Zero hardcoded secrets in source.
- Removed real credentials from `app.py` and `ad.py` (Gmail, Twilio, OpenAI,
  phone numbers, email addresses). All replaced with env-var reads.
- Hardcoded phone number `+919876543210` and email `calebkclas@gmail.com`
  removed from chatbot safety responses and email templates.
- Flask `SECRET_KEY` now read from `SECRET_KEY` env var.
- `machines.db` untracked from git (`git rm --cached`).
- `.gitignore` updated to include `machines.db`.

### Fixed
- **Interim lockdown** — `/api/emergency-call/*`, `/debug/test-call/*`, and
  `/debug/test-email/*` gated behind `ENABLE_EMERGENCY_ENDPOINTS` config flag
  (defaults to `false`). All `/debug/*` routes gated behind `ENABLE_DEBUG_ROUTES`
  (defaults to `false`). Satisfies HARD RULE #4 until F3 auth lands.
- `TwilioVoiceService.__init__` now catches client-init failures gracefully
  instead of crashing the app (HARD RULE #7 — graceful degradation).

### Changed
- Moved `templates/industrial_chatbot.py` to `chatbot/industrial_chatbot.py`
  (application code was misplaced in templates directory).
- Archived `templates/old-dash.html` to `archive/old-dash.html`.
- Created `requirements.txt` with pinned dependency ranges.
- Initialized Alembic with baseline migration for `machines`, `sensor_readings`,
  and `alerts` tables.

### Added
- `config.py` — centralized, env-driven configuration with fail-fast validation.
- `.env.example` — documented template for all required/optional env vars.
- `.env` — dev demo config with placeholder values (never commit real secrets).
- `tests/` — pytest scaffolding with `conftest.py` (Flask test client, in-memory
  DB fixtures).
- `tests/test_anomaly_detection.py` — 15 characterization tests for
  `detect_simple_anomaly()` covering normal range, below-range, above-range,
  sabotage mode, and edge cases.
- `tests/test_alerting.py` — characterization tests for Alert/Machine/SensorReading
  models, serialization, rate-limiting globals, and interim lockdown behaviour.
- `CHANGELOG.md` (this file).

---

## [F1 — Unified codebase] — 2026-07-23

### Changed
- **F1** — Merged `app.py` + `ad.py` into a single entrypoint. All unique code
  from `ad.py` ported to `app.py`: `SensorHealthTracker` (ORM-based),
  sensor-health routes (`/api/machine/<id>/sensor-health`, `/api/machine/<id>/live-stream`,
  `/api/machine/<id>/chart-data`, `/api/machine/<id>/chart-data-simple`,
  `/api/sensor/<id>/<type>/set-maintenance`), `initialize_all_sensor_health()`,
  email alert functions (`send_maintenance_health_alert`,
  `send_critical_sensor_shutdown_alert`, `send_individual_sensor_maintenance_alert`),
  and debug utilities (`/debug/reset-sensor-health`, `/debug/check-sensor-health-table`,
  `/debug/test-chart-endpoint`, `/debug/fix-sample-data`).
- `SensorHealthTracker` now uses SQLAlchemy ORM (`SensorHealth` model) instead of
  raw `sqlite3` — satisfies HARD RULE #6 (no hardcoded DB paths in app logic).
- `set_individual_sensor_maintenance_alert` bug fixed: method added to
  `EnhancedEmailService` and wired into the `/api/sensor/.../set-maintenance` route.
- Backward-compatible `/api/sensor/.../maintenance` URL alias added alongside
  `/api/sensor/.../set-maintenance`.
- Baseline Alembic migration fixed: `DROP TABLE IF EXISTS sensor_health` for
  fresh-DB compatibility.

### Added
- `SensorHealth` ORM model in `app.py` (replaces raw-sqlite3 table from `ad.py`).
- `tests/test_f1_unification.py` — 15 characterization tests for SensorHealth
  model, SensorHealthTracker, `initialize_all_sensor_health()`, and unified routes.
- Alembic migration `402a10f6c87e` for `sensor_health` table.

### Removed
- `ad.py` — deleted after all unique code ported to `app.py`. HARD RULE #5
  satisfied: no parallel "advanced" file.

### Test Results
- **47/47 tests passing** (15 anomaly detection + 12 alerting/lockdown + 15 F1
  unification + 5 SensorHealth model/tracker).

---

## [F3 — Auth, RBAC & audit logging] — 2026-07-24

### Added
- **F3** — Flask-Login based authentication with 4 roles: viewer / operator /
  maintainer / admin. First registered user becomes admin automatically.
- `User` model with password hashing (Werkzeug), role-based access, and active flag.
- `AuditLog` model — append-only log recording mode changes, logins, registrations,
  and notification triggers.
- `log_audit()` helper for writing audit records with user context and IP address.
- `/login`, `/logout`, `/register` routes with flash-message feedback.
- `_require_role()` decorator: money/human-contacting endpoints (`/api/emergency-call/*`,
  `/debug/test-call/*`, `/debug/test-email/*`) now require `operator+` role.
- `/api/machine/<id>/mode` requires `operator+` (mode changes are security-relevant).
- `login.html` and `register.html` templates (Bootstrap 5, consistent with base.html).
- Updated `base.html` navbar: shows username + role for logged-in users, login link
  for anonymous visitors. Fixed `alerts_page` endpoint name bug in nav.
- `unauthorized_handler` returns 401 JSON for API routes, redirects for browser routes.
- `config.py`: `ENABLE_AUTH` flag (default `true`).
- Alembic migration `17a942d570e8` for `users` and `audit_log` tables.

### Changed
- Interim Phase-0 lockdown (ENABLE_EMERGENCY_ENDPOINTS / ENABLE_DEBUG_ROUTES) now
  stacks with auth — both must pass for access.

---

## [F18 — Docker, CI & observability] — 2026-07-24

### Added
- **F18** — Dockerfile (Python 3.11-slim, non-root user, HEALTHCHECK) and
  `docker-compose.yml` (app + PostgreSQL 16 with health checks).
- `/healthz` liveness probe (200 if process running).
- `/readyz` readiness probe (checks DB connectivity, returns component status).
- `structured_logging.py` — JSON and text formatters; `setup_logging()` configures
  root logger with level/format control; noisy loggers suppressed.
- `.dockerignore` for clean builds.

### Test Results
- **115/115 tests passing** (15 anomaly detection + 12 alerting/lockdown + 15 F1
  unification + 5 SensorHealth + 21 F3 auth/RBAC/audit + 6 F18 health/logging
  + 11 F5 timeseries rollups/purge + 18 F4 ingestion driver/pipeline
  + 13 F16 SSE real-time push).

---

## [F5 — Time-series storage, rollups & retention] — 2026-07-24

### Added
- **F5** — `ReadingRollup` model: stores aggregated readings at 1-min or 1-hour
  resolution with min/max/avg/count/anomaly_count per window.
- `rollup_readings(interval, lookback_minutes)`: aggregates raw `SensorReading` rows
  into `ReadingRollup` buckets. Uses string-substring bucketing for SQLite compatibility.
  Upserts on duplicate windows (idempotent).
- `purge_old_readings(raw_days, rollup_1min_days)`: deletes raw readings older than
  `raw_days` (default 7) and 1-min rollups older than `rollup_1min_days` (default 90).
  1-hour rollups retained for 2 years.
- `/api/machine/<id>/rollups` — GET endpoint returns rollup data, filterable by
  `interval`, `sensor_type`, and `hours` lookback window.
- `/api/maintenance/rollups` — POST endpoint manually triggers rollup + purge.
- Background data generation loop now triggers 1-min rollups every ~60s and
  1-hour rollups + purge every ~5min.
- Alembic migration `bf2c38a78f40` for `reading_rollups` table with unique constraint
  and composite index.
- 11 new tests covering model, rollup function, purge function, and API endpoints.

---

## [F4 — Real sensor ingestion: driver interface & pipeline] — 2026-07-24

### Added
- **F4** — `ingestion/` package with pluggable sensor data driver architecture.
- `ingestion/drivers.py` — `SensorDriver` protocol (`connect/read/close`) and
  `Reading` dataclass with validation (quality ∈ {good,uncertain,bad}, finite values).
- `ingestion/simulator.py` — `SimulatorDriver` implementing `SensorDriver`; wraps
  existing data generation logic. Same simulation fidelity, new pluggable shape.
- `ingestion/pipeline.py` — `IngestionPipeline`: validates readings, resolves
  machine_ref → machine_id via optional tag map, rejects bad-quality readings,
  persists to DB, and generates alerts for critical anomalies.
- `SensorReading` model gains `source` (driver name) and `quality` (good/uncertain/bad)
  columns. Added to both `app.py` and `models/database.py`.
- Background data generation loop now uses `SimulatorDriver` → `IngestionPipeline`
  instead of direct `generate_machine_data()` calls (backward-compatible behavior).
- Alembic migration `e779e724d869` for `source` and `quality` columns on `sensor_readings`.
- 18 new tests: Reading validation, SimulatorDriver, IngestionPipeline quality gating,
  tag-map resolution, stats tracking, and driver→pipeline→DB integration.

---

## [F16 — Real-time push transport (SSE)] — 2026-07-24

### Added
- **F16** — `realtime/` package with Server-Sent Events streaming.
- `realtime/stream.py` — `generate_events()` generator yields SSE-formatted events
  (reading, alert, health, heartbeat) by polling the DB for new data since last check.
  Configurable poll interval (1–30s), optional machine_id filter.
- `/api/events` — SSE endpoint returning `text/event-stream` with proper headers
  (no-cache, keep-alive, no-buffering). Accepts `machine_id` and `poll` query params.
- Dashboard JS (`dashboard.html`) now uses `EventSource` for SSE when available,
  with automatic reconnection and exponential backoff (1s → 30s max). Falls back
  to the original 2-second `setInterval` polling if EventSource is unavailable.
- SSE events: `reading` (batched by machine), `alert` (new alerts with notification),
  `health` (sensor health updates), `heartbeat` (keep-alive when idle).
- 13 new tests: event formatting, helper functions (max_id, new readings/alerts),
  SSE endpoint status/headers, machine filtering, poll interval clamping.

---

## [F6 — Historical replay & scenario engine] — 2026-07-24

### Added
- **F6** — `ingestion/replay.py` with `ReplayDriver` and `ScenarioEngine`.
- `ReplayDriver` — replays stored readings from DB at configurable speed (0.1x–100x).
  Connects to DB, reads a time window, yields `Reading` objects with `source="replay(...)"`.
  Tracks progress (0.0–1.0), supports machine_id filtering.
- `ScenarioEngine` — generates synthetic fault-injection readings from JSON scenario definitions.
  Supports 5 fault patterns: `sensor_drift`, `sudden_spike`, `stuck_at`,
  `bearing_degradation`, `intermittent_fault`. Faults are time-indexed and stackable.
- `Scenario` / `ScenarioStep` dataclasses with `to_dict()` serialization.
- Scenario file I/O: `load_scenario()`, `save_scenario()`, `list_scenarios()`.
- `scenarios/` directory with 3 built-in scenarios: `bearing_degradation.json`,
  `sensor_drift.json`, `multi_fault.json`.
- Admin API endpoints (all require `@login_required` + admin role):
  - `POST /api/admin/replay` — load readings from DB for replay.
  - `GET /api/admin/scenarios` — list available scenario files.
  - `GET /api/admin/scenario/<name>` — get scenario details.
  - `POST /api/admin/scenario/<name>/run` — run a scenario, inject readings into DB.
- 24 new tests: ReplayDriver connect/read/filter/close, ScenarioEngine generation
  for 4 fault patterns, scenario file I/O, fault pattern validation, API endpoints
  (missing params, empty window, missing files, auth checks).

---

## [F7 — ML anomaly detection (unsupervised)] — 2026-07-24

### Added
- **F7** — `detection/` package with `detection/ml.py`.
- `Detection` dataclass — unified contract: `is_anomaly`, `anomaly_score` (0–1),
  `detector` name, `explanation`, `contributing_sensors`, `confidence`.
  Serializes via `to_dict()`.
- `IsolationForestDetector` — trains per machine type on healthy history.
  Saves/loads model artifacts via `joblib` to `models/ml/`. Score mapped to [0, 1].
- `HybridDetector` — fuses ML + hard-limit rules. Rules always win: if a hard-limit
  breach is detected, score=1.0 and explanation cites the rule. ML provides nuance
  for softer anomalies. `_rank_contributing()` returns z-score deviations per sensor.
- `HARD_LIMITS` — per-machine-type safety limits that ML must never override.
  Covers Chemical Reactor (temperature, pressure, flow_rate), Biotech Fermenter
  (temperature, pH), Distillation Column (temperature_top/bottom, pressure).
- `detect_anomaly()` convenience function used by ingestion pipeline.
- Admin API endpoints (require auth + role):
  - `POST /api/admin/ml/train` — train Isolation Forest from historical readings.
    Accepts `machine_id`, `hours`, `contamination`.
  - `GET /api/admin/ml/detect/<machine_id>` — run detection on latest readings.
  - `GET /api/admin/ml/status` — which models are trained/available.
- 24 new tests: Detection contract, IsolationForest train/predict/save/load,
  HybridDetector normal/breach/ML-anomaly/unknown-machine fallback,
  convenience function, API endpoints (status, train, detect, e2e train→detect).
