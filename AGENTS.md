# AGENTS.md — Build Guide for AI Coding Agents

> Canonical brief for any AI coding agent working on **PRISM**
> (OpenCode, Codex, Cursor, Claude Code, etc.).
> **Claude Code users:** copy or symlink this to `CLAUDE.md` — content is identical.
>
> Read this file, `ARCHITECTURE.md`, `FEATURES.md`, and `ROADMAP.md` before writing code.

---

## 1. What you are building

**PRISM** (Predictive Industrial Safety & Monitoring) is a Flask-based predictive maintenance and
safety monitoring platform for industrial plants. It ingests sensor data from industrial machines,
detects anomalies, tracks sensor health degradation, and escalates through multi-channel alerts
(email, voice call, SMS). It includes an operator-facing chatbot for diagnostics.

A working prototype exists. **Your job is to upgrade it, not rebuild it.** The 20 upgrades are
specified in `FEATURES.md` and sequenced in `ROADMAP.md`.

---

## 2. Non-negotiable constraints (HARD RULES)

If a task appears to require breaking one of these, **stop and flag it** instead.

1. **PRISM is decision-support, NOT a safety instrumented system (SIS).**
   It must never be represented as, or wired as, a SIL-rated protective function under
   IEC 61511/61508. It does not actuate equipment. It advises humans. Never add code that
   automatically trips, shuts down, or controls physical plant equipment. Never remove the
   human acknowledgment step from an alert path. Keep this disclaimer visible in the UI.

2. **Alerts must never be silently dropped.**
   Suppression, dedup, and rate limiting are allowed — but every suppressed alert must still be
   persisted, counted, and visible in the UI. A false negative in this domain can mean equipment
   damage or injury. If in doubt, surface it.

3. **No credentials in source. Ever.**
   All secrets (SMTP, Twilio, API keys) come from environment/`.env` (gitignored) or a secrets
   store. Never commit, log, or print a secret. Never echo them in debug endpoints.
   If you find a hardcoded credential, flag it immediately and treat it as compromised.

4. **Any endpoint that costs money or contacts a human must be authenticated and rate-limited.**
   This includes emergency calls, SMS, test-email/test-call debug routes. Unauthenticated
   triggering of Twilio is an abuse and billing vector. Debug routes must be disabled in
   production by config, not by comment.

5. **One codebase.** `app.py` and `ad.py` are a hard fork and must be unified (F1). After F1,
   never reintroduce a parallel "advanced" file. Differences become config flags.

6. **Real data path must stay pluggable.** The simulator is one driver among several
   (MQTT/OPC-UA/Modbus). Never hardcode simulation assumptions into detection, storage, or UI.

7. **Graceful degradation.** If SMTP, Twilio, the ML model, or a broker is unavailable, the
   system logs, falls back (e.g. rule-based detection, queued notification), and keeps running.
   Monitoring must not crash because a notifier is down.

---

## 3. Existing repository layout (audit before trusting this)

```
PRISM/
├── app.py                 # 1,831 lines — routes, alerting, chatbot, data gen (TO BE SPLIT, F1)
├── ad.py                  # 2,483 lines — fork of app.py + SensorHealthTracker (TO BE MERGED, F1)
├── machines.db            # SQLite (auto-generated; should NOT be committed)
├── models/
│   ├── database.py        # SQLAlchemy ORM models
│   └── data_generator.py  # standalone data generation
├── templates/
│   ├── base.html, index.html, dashboard.html, chat.html, contact.html
│   ├── old-dash.html      # legacy — delete or archive out of templates/
│   └── industrial_chatbot.py   # ⚠ Python module misplaced inside templates/ — move to app code
├── static/css/dashboard.css
└── README.md, LICENSE, .gitignore
```

Known structural defects to fix during Phase 0 (see `ROADMAP.md`):
- `templates/industrial_chatbot.py` is application code in a template directory.
- `old-dash.html` is dead weight in the active template path.
- `machines.db` is generated state and must be gitignored.
- Business logic, routes, alerting, and the chatbot all live in one module.

> **Always map to the real repo first.** If actual paths differ, report the mapping and do not
> silently move files.

---

## 4. Tech stack (do not swap without approval)

**Backend:** Python 3.7+ (target 3.10+), Flask, Flask-SQLAlchemy, SQLAlchemy ORM, SQLite (dev).
**Notifications:** SMTP (Gmail), Twilio (voice + SMS).
**Frontend:** Jinja2 templates, Bootstrap 5.3, Chart.js 4.4, Plotly.js, Font Awesome, AOS.
**Background work:** daemon threads (to be replaced by a proper scheduler/worker — see F18).

New dependencies must be: actively maintained, permissively licensed, and justified in the PR.
Flag GPL/AGPL before integrating.

---

## 5. Data contracts you must not break

Extend additively; do not rename/remove fields without updating every consumer (dashboard JS,
chatbot, API clients).

- **`machines`**: `id, name, machine_type, description, location, status, is_active, created_at, updated_at`
  where `status ∈ {normal, maintenance, sabotage, shutdown}`.
- **`sensor_readings`**: `id, machine_id, sensor_type, value, unit, is_anomaly, anomaly_score, timestamp`.
- **`alerts`**: `id, machine_id, alert_type, severity, title, message, sensor_data(JSON),
  is_acknowledged, email_sent, sms_sent, created_at, resolved_at`.
- **`sensor_health`** (from `ad.py`, becomes core after F1): `machine_id, sensor_type,
  health_percentage, last_updated, status`.
- **Anomaly score** stays `0.0–1.0`; thresholds `<0.3 normal`, `0.3–0.7 warning`, `>0.7 critical`.
- **REST API paths** under `/api/...` must remain backward compatible; add versioning (`/api/v2`)
  rather than breaking existing routes.

New in the upgrades: readings/alerts gain `source` (which driver produced it) and detections gain
`detector` + `explanation` (see F4, F7, F11).

---

## 6. Definition of Done (every task)

- [ ] Meets the acceptance criteria in `FEATURES.md`.
- [ ] Respects all HARD RULES in §2.
- [ ] Tests added — `pytest` for logic/API, plus a test for the failure/fallback path.
- [ ] Type hints on new/changed Python; no bare `except:`.
- [ ] No secrets in code, logs, or fixtures. No `machines.db` or `.env` committed.
- [ ] Any money-spending or human-contacting path is authenticated + rate-limited + logged.
- [ ] Docstrings + a `CHANGELOG.md` entry referencing the feature ID.
- [ ] Migration provided if the schema changed (Alembic — see F5).

---

## 7. Working style

- **Small, reviewable PRs.** One feature per branch: `feat/F7-ml-anomaly-detection`.
- **Read before writing.** Match existing patterns; don't introduce a second way to do something.
- **Prefer measured over asserted.** Any accuracy/performance claim must come from the evaluation
  harness (F10), not from a hand-written number in a template or README.
- **Threads are a known weak point.** Prefer explicit scheduling and safe DB sessions over adding
  more bare daemon threads.

---

## 8. What NOT to do

- Do not add automatic control/actuation of physical equipment.
- Do not suppress an alert without persisting and surfacing it.
- Do not commit secrets, `machines.db`, or `.env`.
- Do not leave debug/test endpoints reachable without auth.
- Do not fork the app into a second "advanced" file again.
- Do not publish unsubstantiated performance claims (e.g. "90% failure prediction") in UI or docs.
