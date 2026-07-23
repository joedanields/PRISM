# ARCHITECTURE.md — PRISM System Design

Current architecture, target architecture after the 20 upgrades, and the contracts that hold it
together. Read with `AGENTS.md` and `FEATURES.md`.

---

## 1. Current architecture (baseline)

```
                       ┌───────────────── Flask monolith (app.py / ad.py) ─────────────────┐
 daemon thread  ──3s──▶│ generate_sensor_values(mode) ──▶ detect_simple_anomaly()          │
 (data generation)     │        │                                 │                        │
                       │        ▼                                 ▼                        │
                       │  sensor_readings (SQLite)          alerts (SQLite)                │
                       │                                          │                        │
                       │                              ┌───────────┴───────────┐            │
                       │                     EnhancedEmailService     TwilioVoiceService   │
                       │                     (SMTP, daemon thread)    (calls + SMS)        │
                       │                                                                    │
                       │  IndustrialChatbot ── keyword intent → DB context → template reply │
                       │  Flask routes: / /dashboard /chat /contact /api/* /debug/*         │
                       └────────────────────────────┬───────────────────────────────────────┘
                                                    │ 2s polling (fetch)
                                       Jinja2 + Bootstrap + Chart.js/Plotly dashboard
```

**Known weaknesses baked into this design**

| Area | Problem |
|------|---------|
| Codebase | `app.py` / `ad.py` hard fork; ~4,300 duplicated lines |
| Structure | routes + alerting + chatbot + generation in one module; `industrial_chatbot.py` inside `templates/` |
| Security | no auth; `/api/emergency-call/*` and `/debug/test-call/*` publicly triggerable; credentials in source |
| Data | simulation only; no real-sensor path; SQLite grows unbounded; no retention/downsampling |
| Detection | fixed-threshold rules only; no learning, no multivariate correlation, no explanation |
| Alerting | rate limiting via in-memory global sets — lost on restart, not thread-safe, no escalation/SLA |
| Transport | 2-second polling for every panel; no push |
| Ops | no tests, no migrations, no containerization, no CI, no metrics/observability |

---

## 2. Target architecture (after upgrades)

✦ = new or substantially reworked.

```
        Field / plant                     PRISM core                          Users
 ┌──────────────────────┐    ┌────────────────────────────────┐    ┌────────────────────┐
 │ MQTT broker      ✦   │    │  Ingestion layer ✦             │    │ Operator dashboard │
 │ OPC-UA server    ✦   │───▶│   drivers: mqtt|opcua|modbus|  │    │  (SSE/WebSocket ✦) │
 │ Modbus devices   ✦   │    │            simulator           │    │ Work orders ✦      │
 │ Simulator (dev)      │    │   normalize → validate → tag   │    │ KPI / OEE view ✦   │
 └──────────────────────┘    │            source              │    │ Chatbot (RAG ✦)    │
                             └───────────────┬────────────────┘    └────────▲───────────┘
        Edge agent ✦                         ▼                              │
   (store-and-forward)          ┌────────────────────────────┐              │ SSE/WS ✦
                                │ Time-series store ✦        │              │
                                │ raw → rollup → retention   │              │
                                └───────────┬────────────────┘              │
                                            ▼                               │
             ┌──────────────────────────────────────────────┐               │
             │ Detection layer ✦                            │               │
             │  rules  +  ML (IsolationForest / autoencoder) │───────────────┘
             │  + multivariate RCA ✦  + RUL ✦  + explain ✦  │
             │  drift monitoring ✦   eval harness ✦         │
             └───────────────────┬──────────────────────────┘
                                 ▼
             ┌──────────────────────────────────────────────┐
             │ Alerting & escalation ✦                      │
             │  dedup/suppression (durable ✦) → severity →  │
             │  on-call rota ✦ → email / SMS / voice →      │
             │  ack SLA + escalate ✦ → audit log ✦          │
             └──────────────────────────────────────────────┘

     Cross-cutting ✦: auth + RBAC, secrets management, plant/site hierarchy,
                      Docker + CI, structured logging + metrics, Alembic migrations
```

---

## 3. Target module layout (after Phase 0 + F1)

```
prism/
├── app.py                  # thin entrypoint / app factory only
├── config.py               # env-driven settings; feature flags (replaces app.py vs ad.py)
├── core/
│   ├── models.py           # SQLAlchemy models (single source of truth)
│   ├── db.py               # session/engine management
│   └── schemas.py          # serialization contracts
├── ingestion/
│   ├── base.py             # Driver interface
│   ├── simulator.py        # current generator, as a driver
│   ├── mqtt.py  opcua.py  modbus.py        # F4
│   └── pipeline.py         # normalize, validate, tag source
├── detection/
│   ├── rules.py            # detect_simple_anomaly, refactored
│   ├── ml.py               # F7  IsolationForest / autoencoder
│   ├── rul.py              # F8
│   ├── rca.py              # F9  multivariate correlation
│   ├── explain.py          # F11
│   └── eval.py             # F10 harness + drift
├── health/tracker.py       # SensorHealthTracker (promoted from ad.py)
├── alerting/
│   ├── engine.py           # severity, dedup, suppression (F13)
│   ├── escalation.py       # on-call rota, ack SLA (F12)
│   └── channels/{email,sms,voice}.py
├── api/                    # blueprints: machines, readings, alerts, chat, admin
├── auth/                   # F3 users, roles, sessions, audit
├── chatbot/                # moved out of templates/; RAG in F19
├── workorders/             # F14
├── analytics/oee.py        # F15
├── realtime/stream.py      # F16 SSE/WebSocket
├── templates/  static/
├── migrations/             # Alembic
└── tests/
```

---

## 4. Key contracts

### 4.1 Ingestion driver interface (F4)

```python
class SensorDriver(Protocol):
    name: str                      # "mqtt" | "opcua" | "modbus" | "simulator"
    def connect(self) -> None: ...
    def read(self) -> Iterable[Reading]: ...   # yields normalized readings
    def close(self) -> None: ...

@dataclass
class Reading:
    machine_ref: str      # external tag/topic → resolved to machine_id
    sensor_type: str
    value: float
    unit: str
    timestamp: datetime
    source: str           # driver name  ← NEW, persisted on sensor_readings
    quality: str = "good" # good | uncertain | bad   ← from OPC-UA/Modbus quality flags
```

### 4.2 Detection result (F7/F11)

```python
@dataclass
class Detection:
    is_anomaly: bool
    anomaly_score: float          # 0.0–1.0, unchanged semantics
    detector: str                 # "rules" | "isolation_forest" | "autoencoder" | "hybrid"
    explanation: str              # human-readable reason  ← surfaced in UI + alert body
    contributing_sensors: list[str]
    confidence: float
```

Rule thresholds stay authoritative for hard safety limits; ML augments, never overrides a
hard-limit breach (see `AGENTS.md §2`).

### 4.3 Alert lifecycle (F12/F13)

```
raised → (dedup/suppress?) → notified(channel…) → acknowledged(by,user,at)
       → resolved | escalated(level+1) → closed
```
Every transition is persisted and audit-logged. Suppressed alerts are still stored with
`suppressed_reason` and counted in the UI.

### 4.4 API compatibility

Existing `/api/*` routes keep working. New/changed shapes go under `/api/v2/*`.
Debug routes move under `/admin/*`, require auth, and are disabled unless `ENABLE_DEBUG_ROUTES=true`.

---

## 5. Storage strategy (F5)

| Tier | Retention | Resolution | Purpose |
|------|-----------|-----------|---------|
| raw | 7–30 days (config) | per-reading (3s) | live dashboard, incident forensics |
| 1-min rollup | 90 days | min/max/avg/count | trends, RCA |
| 1-hour rollup | 2 years | min/max/avg/count | KPI, OEE, model training |

SQLite remains the default for dev/demo. Provide a `DATABASE_URL` path to PostgreSQL (optionally
TimescaleDB) for production. Never let raw readings grow unbounded — a retention job is part of F5.

---

## 6. Threading & concurrency notes

Current design uses bare daemon threads for generation, email, and Twilio. Target:

- Ingestion runs as a managed worker loop with its own scoped DB session.
- Notification sends go through a queue with retry + backoff, not fire-and-forget threads.
- Rate limiting / dedup state moves out of in-memory global sets into the DB (F13) so it survives
  restarts and is safe across workers.
- Any SQLite deployment must set a busy timeout and serialize writes; concurrency is the known
  failure mode when adding workers.
