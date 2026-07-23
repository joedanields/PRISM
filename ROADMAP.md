# ROADMAP.md — PRISM Implementation Plan

Phased build order for the 20 upgrades in `FEATURES.md`. Each phase leaves the system working.

**How to use with agents.** Point the base-code agent (OpenCode/Codex) at **Phase 0 + Phase 1**
only. Review, then hand to Claude Code to harden and continue through Phases 2–4. Never start a
feature whose dependency is unbuilt (see `FEATURES.md` dependency summary).

---

## ⚠️ Phase 0 — Stop the bleeding *(do before anything else)*

Security and structure. No new user-facing features.

- [ ] **Secret audit (do first).** Scan the working tree *and git history* for real SMTP/Twilio/API
      credentials. **If any real credential was ever committed, rotate it immediately** — it is
      compromised regardless of later edits. Record the exposure in the PR.
- [ ] `git rm --cached machines.db`; add `machines.db`, `.env`, `*.pyc`, `__pycache__/` to `.gitignore`.
- [ ] **F2 — Secrets management.** `.env` + `.env.example` + validated `config.py`; fail fast on
      missing required secrets.
- [ ] **Lock down the money endpoints (interim).** Until F3 lands, gate `/api/emergency-call/*`,
      `/debug/test-call/*`, and `/debug/test-email/*` behind a config flag defaulting to **off**.
- [ ] Test scaffolding: `pytest`, fixtures, a characterization test capturing current anomaly
      detection + alert behavior (needed before F1 refactor).
- [ ] Alembic initialized against the current schema.
- [ ] `CHANGELOG.md` + PR template referencing feature IDs.
- [ ] Move `templates/industrial_chatbot.py` out of `templates/`; archive `old-dash.html`.

**Exit criteria:** no secrets in repo or history (or all rotated); generated DB untracked; no
unauthenticated route can spend money; characterization tests green.

---

## Phase 1 — Credible core ⭐

The jump from "demo" to "defensible system."

- [ ] **F1 — Unify `app.py` + `ad.py`.** Single codebase, modular layout, sensor health in core.
      *Do this before any feature work — everything after is cheaper.*
- [ ] **F3 — Auth, RBAC & audit logging.** Replaces the Phase-0 interim lockdown properly.
- [ ] **F5 — Time-series storage, rollups & retention.** Migrations, rollup tiers, purge job.
- [ ] **F4 — Real sensor ingestion.** Driver interface + simulator refactor + MQTT (OPC-UA/Modbus
      can follow in Phase 2 if time-boxed).
- [ ] **F16 — SSE/WebSocket push.** Retire 2-second polling.
- [ ] **F18 — Docker, CI & observability.** Compose stack, CI with secret scanning, structured logs.

**Exit criteria:** one codebase; login required; real MQTT data flows end-to-end; dashboard is
push-based; `docker compose up` works; CI green. **This is the version you demo.**

---

## Phase 2 — Real intelligence

- [ ] **F6 — Historical replay & scenario engine** (needed to evaluate anything).
- [ ] **F7 — ML anomaly detection** (Isolation Forest / autoencoder, fused with rules).
- [ ] **F10 — Evaluation harness & drift monitoring.**
      *Deliverable: replace or source every performance claim in the UI/README.*
- [ ] **F11 — Explainable, physics-informed hybrid detection.**
- [ ] **F9 — Multivariate correlation & RCA.**
- [ ] Remaining F4 drivers (OPC-UA, Modbus) if deferred from Phase 1.

**Exit criteria:** measured precision/recall/lead-time on labeled scenarios; every alert carries a
plain-language explanation; stuck/flatlined sensors detected; no unsourced accuracy claims remain.

---

## Phase 3 — Operations loop

- [ ] **F13 — Durable dedup, suppression & maintenance windows.**
- [ ] **F12 — Escalation, on-call rota & ack SLA.**
- [ ] **F8 — RUL prediction with uncertainty.**
- [ ] **F14 — Work orders & maintenance scheduling.**
- [ ] **F15 — OEE & reliability KPIs.**

**Exit criteria:** restart-safe suppression with nothing silently dropped; unacked criticals
escalate and stop on acknowledgment; alerts convert to tracked work orders; KPIs computed from real
history.

---

## Phase 4 — Platform & field-readiness

- [ ] **F17 — Multi-plant hierarchy & runtime machine registration.**
- [ ] **F19 — RAG chatbot over manuals/SOPs/incidents** (with citations + persistent history).
- [ ] **F20 — Edge agent with store-and-forward.**

**Exit criteria:** machines addable without code changes; chatbot answers cite source documents;
a 30-minute simulated outage loses zero readings.

---

## Suggested branch names

```
chore/phase0-security-hardening
feat/F2-secrets-management
feat/F1-unify-codebase
feat/F3-auth-rbac-audit
feat/F5-timeseries-retention
feat/F4-ingestion-drivers
feat/F16-realtime-push
feat/F18-docker-ci
feat/F7-ml-anomaly-detection
...
```

## Per-feature Definition of Done (from `AGENTS.md §6`)

Acceptance criteria met · HARD RULES respected (not an SIS · no silent alert drops · no secrets ·
authed money/human endpoints · one codebase · pluggable data path · graceful degradation) · tests
including the failure path · type hints · migration if schema changed · CHANGELOG entry · no
secrets or generated DB committed.

---

## Milestone framing (for a report, demo, or résumé)

- **M0 (Phase 0):** "Secure by default" — no exposed credentials, no free phone calls.
- **M1 (Phase 1):** "One real system" — unified codebase, authenticated, ingesting live MQTT data,
  push dashboard, containerized. *This alone fixes most of the report's own enhancement list.*
- **M2 (Phase 2):** "Actually predictive" — ML detection with measured, explainable results.
- **M3 (Phase 3):** "Closes the loop" — escalation, RUL, work orders, KPIs.
- **M4 (Phase 4):** "Field-deployable" — multi-plant, document-grounded assistant, edge resilience.
