# FEATURES.md — PRISM Upgrade Specifications

20 upgrades that take PRISM from "impressive simulator with alerting" to a credible industrial
monitoring platform. Each is independently shippable.

**Format:** Goal · Why it stands out · Approach · Touches · Libraries · Acceptance · Constraints.
**Effort:** 🟢 low · 🟡 medium · 🔴 high **Priority:** ⭐ = Phase-1 core.

---

## Theme A — Foundation & Security (do these first; everything else depends on them)

### F1 · Unify `app.py` + `ad.py` into one configurable codebase 🟡 ⭐
**Goal.** Eliminate the hard fork. One application, with sensor-health tracking as a config flag.
**Why it stands out.** ~4,300 lines of near-duplicate code is the single biggest drag on the
project; every other feature would otherwise have to be written twice.
**Approach.** Diff both files; promote `SensorHealthTracker` and time-based degradation from `ad.py`
into core. Split the monolith into the module layout in `ARCHITECTURE.md §3`. Move
`templates/industrial_chatbot.py` into `chatbot/`. Archive `old-dash.html` out of `templates/`.
Behavior-preserving: both old entrypoints' features remain reachable via config.
**Touches.** everything — do it before feature work.
**Acceptance.** `ad.py` deleted; a single entrypoint reproduces both modes via config; no file over
~500 lines; app starts and the dashboard behaves identically; characterization tests pass.
**Constraints.** No behavior change beyond structure. Never reintroduce a parallel "advanced" file.

### F2 · Secrets management & credential hygiene 🟢 ⭐
**Goal.** Zero credentials in source; environment-driven config; rotate anything exposed.
**Why it stands out.** Hardcoded SMTP/Twilio credentials are a live billing and security exposure.
**Approach.** `.env` (gitignored) + `.env.example`; `config.py` reads env with validation and fails
fast on missing required secrets. `git rm --cached machines.db`. Scan git history for committed
secrets; if any real credential was ever committed, **rotate it** and note the exposure.
**Touches.** `config.py`, all service constructors, `.gitignore`, README setup.
**Libraries.** `python-dotenv`; optionally `detect-secrets` / `gitleaks` in CI.
**Acceptance.** No secret literal anywhere in the repo; app refuses to start with missing required
secrets (clear error); secrets never logged; `.env` and `machines.db` untracked.

### F3 · Authentication, RBAC & audit logging 🟡 ⭐
**Goal.** Log in required; roles (viewer / operator / maintainer / admin); every action attributed.
**Why it stands out.** Today anyone reaching the server can trigger real emergency phone calls.
This closes a genuine abuse vector and is table stakes for any plant deployment.
**Approach.** Flask-Login + password hashing; role-gated routes. **Money/human-contacting endpoints
(`/api/emergency-call/*`, test-email/test-call) require `operator`+ and are rate-limited.** Move
`/debug/*` under `/admin/*`, auth-gated and disabled unless `ENABLE_DEBUG_ROUTES=true`.
Append-only audit log of mode changes, acknowledgments, and notification triggers.
**Touches.** new `auth/`, route decorators, `audit` table, login UI.
**Libraries.** Flask-Login, Werkzeug hashing, Flask-Limiter.
**Acceptance.** Unauthenticated access to control/debug/notification routes returns 401/403; every
mode change and alert acknowledgment records actor + timestamp; audit log is append-only.

---

## Theme B — Real Data (the credibility jump)

### F4 · Real sensor ingestion: MQTT / OPC-UA / Modbus 🔴 ⭐
**Goal.** Accept data from actual industrial sources; make the simulator just one driver.
**Why it stands out.** Turns PRISM from a simulation demo into something that could point at a real
plant — the biggest single leap in seriousness.
**Approach.** Define the `SensorDriver` interface (`ARCHITECTURE.md §4.1`). Implement `simulator`
(refactor of current generator), `mqtt` (topic→tag mapping), `opcua`, `modbus`. Normalize into
`Reading` with `source` and `quality`. Tag-mapping config maps external tags to machine/sensor.
**Touches.** new `ingestion/`, `sensor_readings.source` column, migration, driver config UI/file.
**Libraries.** `paho-mqtt`, `asyncua`, `pymodbus`.
**Acceptance.** Same pipeline runs unchanged against simulator or a live MQTT broker; a test broker
feeds readings end-to-end into dashboard + alerts; bad/uncertain quality flags are respected, not
treated as valid readings; driver failure degrades gracefully and raises a system alert.
**Constraints.** No simulation assumptions leak into detection/storage/UI.

### F5 · Time-series storage, rollups & retention 🟡 ⭐
**Goal.** Stop unbounded growth; add rollups and a retention policy; support PostgreSQL.
**Why it stands out.** At 3-second inserts across 16 sensors, SQLite bloats fast; this is what makes
long-horizon trends and ML training data possible at all.
**Approach.** Alembic migrations. Rollup tables (1-min, 1-hour: min/max/avg/count). Scheduled
retention + downsample job per `ARCHITECTURE.md §5`. `DATABASE_URL` supports SQLite (dev) and
PostgreSQL/TimescaleDB (prod). Charts read from the appropriate tier by time range.
**Touches.** `core/models.py`, `migrations/`, rollup job, chart-data endpoints.
**Libraries.** Alembic, SQLAlchemy, APScheduler; optional TimescaleDB.
**Acceptance.** Raw data older than the configured window is downsampled and purged; a year of
simulated data queries fast; migrations run cleanly forward; no data loss in rollup (counts match).

### F6 · Historical replay & scenario engine 🟡
**Goal.** Replay any past time window (or a scripted fault scenario) through the live pipeline.
**Why it stands out.** Makes demos reproducible, incidents re-investigable, and ML evaluation
possible against known events — and it's a great presentation feature.
**Approach.** Replay driver reads stored/scripted readings at configurable speed (1x…100x) into the
normal ingestion path, isolated from production data. Scenario files define fault injection
(bearing degradation, sensor drift, sudden spike, stuck-at value).
**Touches.** `ingestion/replay.py`, scenario YAML/JSON, admin UI control.
**Acceptance.** A saved incident replays and reproduces the original alerts; replay is clearly
flagged in the UI and never mixes with live data; scenarios are versioned files.
**Depends on.** F4, F5.

---

## Theme C — Real Intelligence

### F7 · ML anomaly detection (unsupervised) 🔴 ⭐
**Goal.** Add learned detection alongside the rules: Isolation Forest and/or an LSTM/dense
autoencoder over multivariate sensor windows.
**Why it stands out.** Directly answers the report's own "Areas for Enhancement" #1 and moves
detection beyond static thresholds — catching drift and correlated faults rules can't see.
**Approach.** Train per machine on healthy-mode history; score live windows; fuse with rules
(**hard-limit breaches always win**). Persist model artifacts with version + training window.
Detection emits the `Detection` contract with `detector` and `explanation`.
**Touches.** `detection/ml.py`, model registry, `sensor_readings`/alert enrichment.
**Libraries.** scikit-learn (IsolationForest), optionally PyTorch/Keras for the autoencoder, joblib.
**Acceptance.** Model trains from stored history via one command; measured precision/recall on the
F10 harness beats rules-only on injected faults; inference adds <100ms per cycle; falls back to
rules if the model is missing/corrupt.
**Constraints.** ML never suppresses a hard-limit alarm. Every ML detection carries an explanation.

### F8 · Remaining Useful Life (RUL) prediction 🔴
**Goal.** Estimate time-to-failure/maintenance per sensor and machine, with uncertainty.
**Why it stands out.** This is what "predictive maintenance" actually means; it upgrades the
existing linear degradation model into a data-driven forecast.
**Approach.** Extend `SensorHealthTracker`: fit degradation trends from rollups, project to
threshold crossing, output RUL with a confidence interval. Feed the work-order scheduler (F14).
**Touches.** `detection/rul.py`, health tracker, dashboard health panel.
**Acceptance.** RUL shown with an explicit uncertainty band, never a bare number; validated against
replayed known-failure scenarios; degrades to the existing rate-based model when data is thin.

### F9 · Multivariate correlation & root-cause analysis 🟡
**Goal.** Explain *why* a machine is anomalous: which sensors moved together, and likely cause.
**Why it stands out.** Turns "temperature is high" into "temperature rising while flow drops →
probable fouling/blockage" — the difference between an alarm and an insight.
**Approach.** Correlation/covariance over recent windows; rank contributing sensors; map known
signatures (per machine type) to candidate causes; attach to alerts and the chatbot.
**Touches.** `detection/rca.py`, alert body, dashboard detail modal.
**Acceptance.** Alerts list ranked contributing sensors; documented fault signatures for at least
the four machine types; RCA output is advisory and labeled as such.
**Depends on.** F7.

### F10 · Evaluation harness & model drift monitoring 🟡 ⭐
**Goal.** Measure detection quality (precision/recall/F1, false-alarm rate, lead time) against
labeled scenarios; monitor drift over time.
**Why it stands out.** Replaces the landing page's unsubstantiated "90% failure prediction" with
numbers you can defend. This is the credibility feature.
**Approach.** Labeled scenario set (from F6) → run pipeline → compute metrics → persist runs →
display trend. Track input distribution drift and alert when the live distribution diverges from
training.
**Touches.** `detection/eval.py`, `/admin/eval` page, metrics tables.
**Libraries.** scikit-learn metrics, scipy (KS test / PSI for drift).
**Acceptance.** One command produces real metrics; results stored and charted over time; **every
performance claim in the UI/README is sourced from a harness run or removed.**
**Depends on.** F6 (scenarios), F7.

### F11 · Explainable, physics-informed hybrid detection 🟡
**Goal.** Combine hard safety limits, physical plausibility checks, and ML into one explained verdict.
**Why it stands out.** Industrial users don't trust black boxes; explainability is an adoption
requirement, not a nicety.
**Approach.** Layer: (1) hard limits, (2) physics/plausibility (e.g. distillation bottom temp must
exceed top temp; heat-exchanger outlet vs inlet consistency; rate-of-change limits; stuck-sensor
detection), (3) ML score. Emit a single `Detection` with a plain-language explanation.
**Touches.** `detection/rules.py`, `detection/explain.py`, alert templates.
**Acceptance.** Each machine type has documented physical constraints that are checked; every alert
states which layer fired and why; a stuck/flatlined sensor is detected even when its value is
in-range.
**Depends on.** F7.

---

## Theme D — Alerting & Operations

### F12 · Alert escalation, on-call rota & acknowledgment SLA 🟡
**Goal.** Escalate unacknowledged critical alerts through a defined chain instead of firing once.
**Why it stands out.** Upgrades impressive one-shot notifications into a real incident-management
loop — the thing plants actually need at 3 a.m.
**Approach.** On-call schedule (contacts, shifts); alert lifecycle per `ARCHITECTURE.md §4.3`;
ack deadline per severity; unacked → escalate to next level (email → SMS → voice → next contact);
full timeline persisted.
**Touches.** `alerting/escalation.py`, on-call config, alert timeline UI.
**Acceptance.** Unacknowledged critical alert escalates on schedule; acknowledgment stops
escalation and is attributed to a user; escalation history visible per incident; escalation is
rate-limited and cannot loop infinitely.
**Depends on.** F3 (identity), F13.

### F13 · Durable dedup, suppression & maintenance windows 🟡
**Goal.** Replace in-memory global rate-limit sets with persisted, restart-safe suppression.
**Why it stands out.** Current flags die on restart and race across threads — meaning either
duplicate 3 a.m. phone calls or silently missed alerts.
**Approach.** DB-backed suppression state keyed by (machine, alert type, fingerprint) with TTL;
flapping detection; scheduled maintenance windows that suppress expected alerts.
**Constraint (hard):** suppressed alerts are still **persisted, counted, and shown** — never dropped.
**Touches.** `alerting/engine.py`, suppression table, dashboard "suppressed" badge.
**Acceptance.** Restart does not resend a suppressed alert; no duplicate notification under
concurrent workers; every suppressed alert is visible with its reason; maintenance windows work.

### F14 · Work orders & maintenance scheduling 🟡
**Goal.** Turn alerts and RUL forecasts into tracked maintenance work orders.
**Why it stands out.** Closes the loop from detection to action — the missing half of a maintenance
system, and what makes it useful rather than informational.
**Approach.** Work order model (machine, sensor, priority, assignee, status, due date, notes,
linked alert). Auto-suggest from critical alerts and RUL thresholds. Kanban/list UI. Completing an
order can reset sensor health.
**Touches.** new `workorders/`, migration, UI page, alert→WO action.
**Acceptance.** Alert can be converted to a work order in one click; RUL breach auto-proposes one;
status transitions audited; completion recorded against the machine's history.
**Depends on.** F3, F8.

### F15 · OEE & reliability KPIs 🟡
**Goal.** Plant-level analytics: availability, MTBF, MTTR, downtime, alert volume/machine, OEE.
**Why it stands out.** Speaks management's language and makes the value of the system measurable.
**Approach.** Compute from alerts, mode history, and work orders over rollups; KPI dashboard with
date ranges and CSV/PDF export.
**Touches.** `analytics/oee.py`, KPI page, export endpoints.
**Acceptance.** KPIs computed from stored history (not hardcoded); date-range filtering; export
works; definitions documented so numbers are auditable.
**Depends on.** F5, F14.

---

## Theme E — Platform & Reach

### F16 · Real-time push transport (SSE/WebSocket) 🟡 ⭐
**Goal.** Replace 2-second polling with server push.
**Why it stands out.** Directly fixes a known weakness; cuts request volume dramatically and makes
the "mission control" dashboard genuinely live.
**Approach.** SSE (simplest for one-way telemetry) or Flask-SocketIO for bidirectional. Publish
reading/alert/health events; client subscribes per machine; auto-reconnect with backoff; fall back
to polling if the connection fails.
**Touches.** `realtime/stream.py`, dashboard JS, alert banner.
**Libraries.** Flask-SSE / Flask-SocketIO.
**Acceptance.** Dashboard updates without polling; measured request reduction documented; reconnect
works after network drop; polling fallback verified.

### F17 · Multi-plant / multi-line hierarchy 🟡
**Goal.** Model Site → Building → Line → Machine → Sensor instead of a flat machine list.
**Why it stands out.** Four hardcoded machines is a demo; hierarchy plus dynamic machine
registration makes it a platform.
**Approach.** Hierarchy tables + migration; machines/sensors configurable at runtime (add a machine
without code changes); scoped dashboards and role scoping per site.
**Touches.** models, migration, admin CRUD UI, dashboard filters, RBAC scoping.
**Acceptance.** A new machine + sensors can be added entirely via UI/config; dashboards filter by
hierarchy; existing four machines migrate cleanly.
**Depends on.** F3, F5.

### F18 · Docker, CI/CD & observability 🟡 ⭐
**Goal.** Containerized deploy, automated tests on every push, structured logs and health metrics.
**Why it stands out.** Fixes three "Areas for Enhancement" at once and makes the project credible to
run anywhere.
**Approach.** Dockerfile + docker-compose (app, Postgres, MQTT broker for dev). GitHub Actions:
lint, tests, secret scan. Structured JSON logging, `/healthz` + `/readyz`, Prometheus-style metrics
(ingestion rate, detection latency, alert counts, notification failures). Replace bare daemon
threads with a managed scheduler/worker.
**Touches.** `Dockerfile`, `docker-compose.yml`, `.github/workflows/`, logging config, metrics.
**Acceptance.** `docker compose up` yields a working stack; CI blocks merge on failing tests or
detected secrets; logs are structured with no PII/secrets; health endpoints reflect real state.

### F19 · RAG chatbot over manuals, SOPs & incident history 🔴
**Goal.** Upgrade the keyword-intent bot into retrieval-augmented Q&A grounded in real documents.
**Why it stands out.** "What's the SOP for reactor overpressure?" answered from the actual plant
manual — far beyond template replies, and genuinely useful on shift.
**Approach.** Ingest equipment manuals/SOPs/past incidents into a vector store; retrieve + generate
via local LLM (Ollama) or configured provider; **always cite the source document/section**; keep
live DB context for status questions; keep the rule-based fallback.
**Touches.** `chatbot/` (moved out of `templates/`), vector store, document ingestion admin.
**Libraries.** ChromaDB/FAISS + sentence-transformers; Ollama for local inference.
**Acceptance.** Answers cite source documents; falls back cleanly when no LLM is available;
persistent chat history (fixes the in-memory limitation); no hallucinated procedure steps —
uncited procedural claims are withheld.
**Constraints.** Safety procedures must be quoted/cited from source, never invented.

### F20 · Edge agent with store-and-forward 🔴
**Goal.** A lightweight agent at the plant that buffers readings during network loss and forwards
on reconnect.
**Why it stands out.** Industrial networks are unreliable; surviving disconnection is what separates
a lab project from a field-deployable one.
**Approach.** Small Python agent: local queue (SQLite/disk), backpressure, batch upload with
idempotency keys, clock-skew handling, TLS + token auth to the central API.
**Touches.** new `edge/` package, ingest batch endpoint, dedup on ingest.
**Acceptance.** Simulated 30-minute outage loses zero readings; duplicates are rejected via
idempotency key; agent runs in a constrained container; timestamps preserved from capture time.
**Depends on.** F4, F18.

---

## Dependency summary

```
F1, F2 ─▶ everything
F3 ─▶ F12, F14, F17
F4 ─▶ F6, F20
F5 ─▶ F6, F15, F17
F6 ─▶ F10
F7 ─▶ F9, F11, F10
F8 ─▶ F14
F13 ─▶ F12
F14 ─▶ F15
F18 ─▶ F20
```

**Phase-1 core (⭐):** F1, F2, F3, F4, F5, F7, F10, F16, F18 — see `ROADMAP.md` for ordering.
