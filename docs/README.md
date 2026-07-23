# PRISM — Predictive Industrial Safety & Monitoring

**AI-driven predictive maintenance and safety monitoring for industrial plants.** PRISM ingests
sensor data from industrial machines, detects anomalies, tracks sensor-health degradation, and
escalates through multi-channel alerts (email, SMS, automated voice calls). An operator-facing
chatbot answers diagnostic questions against live plant data.

- **Author:** Joe Daniel A · **License:** MIT
- **Stack:** Python · Flask · SQLAlchemy · Bootstrap 5 · Chart.js / Plotly · Twilio · SMTP

> **Status:** working prototype undergoing a 20-feature upgrade to a deployment-grade platform.
> See the docs below.

> ⚠️ **PRISM is decision-support, not a safety instrumented system.** It does not control or trip
> equipment and is not SIL-rated under IEC 61511/61508. It advises human operators. Never wire it
> to actuate plant equipment.

---

## 📚 Documentation (read in this order)

| File | Purpose |
|------|---------|
| **[docs/AGENTS.md](./docs/AGENTS.md)** | Build brief for AI coding agents: hard rules, conventions, Definition of Done. **Claude Code: copy to `CLAUDE.md`.** |
| **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** | Current + target architecture, module layout, data contracts, storage strategy. |
| **[docs/FEATURES.md](./docs/FEATURES.md)** | The 20 upgrades, each with acceptance criteria. |
| **[docs/ROADMAP.md](./docs/ROADMAP.md)** | Phased build order, starting with security hardening. |

---

## 🧠 How it works

```
sensors (MQTT / OPC-UA / Modbus / simulator)
      ─▶ ingestion: normalize · validate · tag source
      ─▶ storage: raw → 1-min rollup → 1-hour rollup (retention policy)
      ─▶ detection: hard limits + physics checks + ML  → explained anomaly score
      ─▶ alerting: dedup/suppress → severity → on-call → email/SMS/voice → ack SLA → escalate
      ─▶ dashboard (server push), work orders, KPIs, chatbot
```

Machines monitored in the reference config: Chemical Reactor (R-001), Biotech Fermenter (F-003),
Distillation Column (D-002), Heat Exchanger (HX-005) — 16 sensors total, each with normal and
absolute operating ranges.

---

## 🚦 Non-negotiables (see `docs/AGENTS.md §2`)

- **Not an SIS** — advisory only; never actuates equipment; human acknowledgment always required.
- **No alert is ever silently dropped** — suppressed alerts stay persisted, counted, and visible.
- **No credentials in source** — env/`.env` only; nothing secret logged or committed.
- **Money/human-contacting endpoints are authenticated and rate-limited** — emergency calls, SMS,
  and test routes are never open. Debug routes are config-disabled in production.
- **One codebase** — the `app.py` / `ad.py` fork is being unified; don't reintroduce it.
- **Graceful degradation** — a dead broker, SMTP outage, or missing model must not stop monitoring.

---

## 🏁 Quick start

```bash
cp .env.example .env       # fill in SMTP / Twilio credentials — never commit this file
pip install -r requirements.txt
flask db upgrade           # after Alembic lands (F5)
python app.py              # http://localhost:5000
```

Docker (after F18): `docker compose up`.

---

## 🤝 Handoff workflow

1. **Base code:** point your coding agent (OpenCode / Codex) at `docs/AGENTS.md` +
   `docs/ARCHITECTURE.md`, then **Phase 0 and Phase 1** of `docs/ROADMAP.md`.
   One feature per branch (`feat/F#-...`).
2. **Polish:** hand the result to **Claude Code** (`CLAUDE.md` = `AGENTS.md`) for Phases 2–4.
3. Every change must satisfy the **Definition of Done** in `docs/AGENTS.md §6`.

**Start with Phase 0.** It is a security phase: credential audit and rotation, untracking the
generated database, and closing unauthenticated endpoints that can place real phone calls.

---

## 📄 License

MIT. Third-party services (Twilio, SMTP providers) and any models/datasets retain their own terms.
