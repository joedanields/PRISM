# PRISM: Predictive Industrial Safety & Monitoring AI

## Comprehensive Project Report

---

## 1. Project Overview

**PRISM** is a full-stack, AI-driven predictive maintenance and safety monitoring system designed for industrial environments. It simulates real-time sensor data from four types of industrial machines, detects anomalies using rule-based logic, and triggers multi-channel intelligent alerts (email, voice calls, SMS). The system also features an AI-powered chatbot for interactive diagnostics.

- **Repository:** `github.com/joedanields/PRISM`
- **Author:** Joe Daniel A
- **License:** MIT (2025)
- **Language:** Python 3.7+
- **Framework:** Flask (web), SQLAlchemy (ORM), SQLite (DB)

---

## 2. Architecture

```
PRISM/
├── app.py                  # Main application (1,831 lines) - core logic, routes, alerts
├── ad.py                   # Advanced version (2,483+ lines) - adds sensor health tracking
├── machines.db             # SQLite database (auto-generated)
├── models/
│   ├── __init__.py
│   ├── database.py         # SQLAlchemy ORM models (97 lines)
│   └── data_generator.py   # Standalone data generation module (239 lines)
├── templates/
│   ├── base.html           # Base layout with Bootstrap, Plotly.js, alerts
│   ├── index.html          # Landing page with hero, features, stats (758 lines)
│   ├── dashboard.html      # Mission control dashboard (1,400+ lines)
│   ├── chat.html           # AI chatbot interface (682 lines)
│   ├── contact.html        # Team/contact page (675 lines)
│   ├── old-dash.html       # Legacy dashboard (archived)
│   └── industrial_chatbot.py  # Standalone chatbot module (508 lines)
├── static/css/
│   └── dashboard.css       # Custom dashboard styling
├── README.md
├── LICENSE
└── .gitignore
```

### Execution Modes
| File | Description |
|------|-------------|
| `app.py` | Standard version with 4 machines, alerts, email, Twilio, chatbot |
| `ad.py` | Advanced version adding sensor health tracking, time-based degradation, historical chart data |

---

## 3. Database Design

Three primary tables (defined in `models/database.py` and inline in `app.py`/`ad.py`):

### `machines` Table
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `name` | VARCHAR(100) UNIQUE | Machine name (e.g., "Chemical Reactor R-001") |
| `machine_type` | VARCHAR(50) | Type classification |
| `description` | TEXT | Human-readable description |
| `location` | VARCHAR(100) | Physical plant location |
| `status` | VARCHAR(20) | `normal` / `maintenance` / `sabotage` / `shutdown` |
| `is_active` | BOOLEAN | Whether machine is monitored |
| `created_at` | DATETIME | Record creation timestamp |
| `updated_at` | DATETIME | Last status update |

### `sensor_readings` Table
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `machine_id` | INTEGER FK | References `machines.id` |
| `sensor_type` | VARCHAR(50) | e.g., `temperature`, `pressure`, `ph` |
| `value` | FLOAT | Sensor reading value |
| `unit` | VARCHAR(20) | Unit of measurement |
| `is_anomaly` | BOOLEAN | Whether reading is anomalous |
| `anomaly_score` | FLOAT | 0.0 - 1.0 risk score |
| `timestamp` | DATETIME (indexed) | When reading was taken |

### `alerts` Table
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `machine_id` | INTEGER FK | References `machines.id` |
| `alert_type` | VARCHAR(30) | `warning` / `critical` / `maintenance` / `info` |
| `severity` | VARCHAR(20) | `low` / `medium` / `high` / `critical` |
| `title` | VARCHAR(200) | Alert headline |
| `message` | TEXT | Detailed alert description |
| `sensor_data` | TEXT | JSON-serialized sensor readings |
| `is_acknowledged` | BOOLEAN | Whether operator acknowledged |
| `email_sent` / `sms_sent` | BOOLEAN | Notification tracking |
| `created_at` / `resolved_at` | DATETIME | Timestamps |

### Additional Table (ad.py only)
**`sensor_health`** - Tracks individual sensor degradation over time with columns: `machine_id`, `sensor_type`, `health_percentage` (0-100%), `last_updated`, `status` (`healthy`/`warning`/`degrading`/`critical`/`shutdown`).

---

## 4. Monitored Machines & Sensors

Four industrial machines with 16 total sensors:

### 1. Chemical Reactor (R-001) - Building A, Floor 2
| Sensor | Unit | Normal Range | Min/Max |
|--------|------|-------------|---------|
| Temperature | °C | 250 - 400 | 200 - 800 |
| Pressure | bar | 10 - 30 | 1 - 50 |
| Flow Rate | L/min | 20 - 80 | 5 - 100 |
| Level | mm | 50 - 180 | 0 - 215 |

### 2. Biotech Fermenter (F-003) - Building B, Floor 1
| Sensor | Unit | Normal Range | Min/Max |
|--------|------|-------------|---------|
| Temperature | °C | 35 - 42 | 20 - 60 |
| pH | pH | 6.5 - 7.5 | 5.0 - 9.0 |
| Dissolved Oxygen | % | 20 - 80 | 0 - 100 |
| Agitation | RPM | 100 - 300 | 50 - 500 |

### 3. Distillation Column (D-002) - Building A, Floor 3
| Sensor | Unit | Normal Range | Min/Max |
|--------|------|-------------|---------|
| Top Temperature | °C | 80 - 120 | 50 - 200 |
| Bottom Temperature | °C | 150 - 250 | 100 - 300 |
| Pressure | bar | 0.5 - 2.0 | 0.1 - 5.0 |
| Reflux Ratio | ratio | 2 - 6 | 1 - 10 |

### 4. Heat Exchanger (HX-005) - Building C, Floor 1
| Sensor | Unit | Normal Range | Min/Max |
|--------|------|-------------|---------|
| Inlet Temp | °C | 40 - 90 | 25 - 150 |
| Outlet Temp | °C | 50 - 120 | 30 - 180 |
| Pressure Drop | bar | 0.2 - 1.5 | 0.1 - 3.0 |
| Flow Rate | L/min | 40 - 160 | 10 - 200 |

---

## 5. Operational Modes

Each machine can be set to one of four modes via the dashboard or API:

| Mode | Behavior | Data Generation Pattern |
|------|----------|------------------------|
| **Normal** | All sensors within normal range | Values generated within `normal_range` with 2% random noise |
| **Maintenance** | Irregular but non-dangerous readings | 40% chance of 15-35% deviation from normal range per reading |
| **Sabotage** | Extreme, dangerous values | 80% chance of readings near min/max (85%+ of range extremes) |
| **Shutdown** | All values drop to safe minimum | Fixed at 5% of total range above minimum |

---

## 6. Anomaly Detection Engine

Implemented in `detect_simple_anomaly()` (`app.py:1522-1541`):

**Algorithm:**
1. Calculate deviation: how far outside `[normal_min, normal_max]` a reading falls
2. Normalize deviation against the normal range width
3. Flag as anomaly if deviation > 10% of normal range
4. Score: `min(1.0, deviation)` - ranges from 0.0 (normal) to 1.0 (critical)
5. **Sabotage override:** If value >= 90% of sensor max OR <= 110% of sensor min, force anomaly with score 0.95

**Risk Thresholds:**
- `0.0 - 0.3`: Normal operation
- `0.3 - 0.7`: Attention needed (warning)
- `0.7 - 1.0`: Critical issue (emergency)

---

## 7. Alert & Notification System

### Email Alerts (via Gmail SMTP)

**`EnhancedEmailService`** class (`app.py:46-418`) sends async HTML-formatted emails:

1. **Maintenance Alert** - Triggered when machine is in maintenance mode with irregular readings
   - Recipients: Maintenance Team, Plant Manager
   - Contains: Equipment info, irregular sensor readings with deviation percentages, recommended actions
   - Rate-limited: One email per machine per mode activation

2. **Sabotage Incident Report** - Triggered on critical sabotage detection (2+ sensors with score > 0.8)
   - Recipients: Emergency Response, Plant Manager, Maintenance Team
   - Contains: Incident ID, timeline, critical sensor readings, pre-incident historical data table, emergency action protocols
   - Priority: Critical (X-Priority: 1 headers)
   - Rate-limited: One per machine per sabotage event

### Voice Calls & SMS (via Twilio)

**`TwilioVoiceService`** class (`app.py:442-598`):

1. **Emergency Calls** - Automated voice calls to all 3 emergency contacts
   - Professional incident message with machine name, time, details
   - TwiML-based interactive response (press key to acknowledge)
   - 30-second timeout, call recording enabled
   - 5-second delay between calls

2. **SMS Backup** - Sent 30-45 seconds after emergency calls
   - Contains incident summary + dashboard link
   - Sent to all emergency contacts

3. **Maintenance Reminder Calls** - Friendly voice reminders for scheduled maintenance
   - Sent to primary contact only

### Rate Limiting
Global sets (`sent_maintenance_emails`, `sent_sabotage_emails`, `sent_twilio_calls`) prevent email/SMS spam. Flags reset when machine mode changes back to normal.

---

## 8. AI Chatbot (MaintenanceBot)

**`IndustrialChatbot`** class (`app.py:633-1034`):

### Capabilities
- Equipment diagnostics and troubleshooting
- Real-time status checks (queries database for latest readings)
- Safety protocols and emergency procedures
- Anomaly analysis with risk scoring
- Predictive maintenance insights
- General help and guidance

### NLP Pipeline
1. **Intent Detection** - Keyword-based classification into 7 intents: `machine_status`, `troubleshooting`, `maintenance`, `anomaly_analysis`, `safety`, `predictions`, `general_help`
2. **Entity Extraction** - Regex pattern matching to identify which machine the user is referring to (reactor/fermenter/column/exchanger)
3. **Context Gathering** - Queries database for current machine status and recent sensor readings
4. **Response Generation** - Template-based responses enriched with real-time data from the database

### Configuration
- Supports OpenAI API or local Ollama models (llama2/mistral)
- Default mode: Local AI with rule-based fallback
- Conversation history stored in memory per session

### Web Interface (`chat.html`)
- Split-panel layout: sidebar with quick actions + system overview, main chat area
- Real-time typing indicators
- Markdown-style formatting (bold, italic, code)
- Quick suggestion buttons
- Auto-scrolling message feed

---

## 9. Sensor Health Tracking (ad.py only)

**`SensorHealthTracker`** class (`ad.py:1513-1682`):

### Degradation Model
Each sensor type has a configurable hourly degradation rate:
| Sensor | Degradation Rate (%/hr) |
|--------|------------------------|
| pH | 0.8 (fastest) |
| Dissolved Oxygen | 0.6 |
| Temperature (all) | 0.5 |
| Flow Rate | 0.4 |
| Pressure (all) | 0.3 |
| Reflux Ratio | 0.3 |
| Level | 0.2 |
| Agitation | 0.1 (most stable) |

### Health States
- `healthy`: >= 80%
- `warning`: 50% - 80%
- `degrading`: 20% - 50%
- `critical`: < 20%
- `shutdown`: 0%

### Mode Effects on Health
- **Normal**: Health resets to 100%
- **Maintenance**: All sensors drop to 30-50% randomly
- **Sabotage**: All sensors drop to 0% (complete failure)

---

## 10. Web Dashboard

### Landing Page (`index.html`)
- Animated gradient hero section with AOS scroll animations
- 6 feature cards (AI Analytics, Real-Time Monitoring, Predictive Insights, Industrial Grade, Smart Alerts, Advanced Analytics)
- Technology stack showcase (Python, Flask, Plotly, SQLAlchemy, JavaScript, Bootstrap)
- Statistics section (75% downtime reduction, 90% failure prediction, 50% cost savings, 24/7 monitoring)
- Responsive design with custom scrollbar

### Mission Control Dashboard (`dashboard.html`)
- Dark-themed professional UI with glassmorphism effects
- **Metrics Header**: Active machines, sensor network, system health, active alerts
- **Machine Panels**: One per machine showing:
  - Real-time sensor values (auto-refreshing every 2 seconds)
  - Color-coded anomaly indicators with glow animations
  - Health progress bar with individual sensor health grid
  - Machine mode controls (Normal/Maintenance/Emergency)
  - Individual sensor maintenance buttons
  - Health Analysis modal
- **Critical Alert Banner**: Auto-displays for critical alerts with audio notification
- Auto-refreshes sensor data every 2s, health data every 2s

---

## 11. REST API Endpoints

### Main Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET | `/dashboard` | Mission control dashboard |
| GET | `/chat` | AI chatbot interface |
| GET | `/contact` | Team/contact page |

### Data API
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/machines` | All active machines |
| GET | `/api/machine/<id>/latest` | Latest sensor readings |
| GET | `/api/machine/<id>/chart-data` | Historical data for charts |
| GET | `/api/machine/<id>/chart-data-simple` | Simplified chart data |
| GET | `/api/machine/<id>/historical-data` | Last 20 readings per sensor |
| GET | `/api/machine/<id>/live-stream` | Real-time sensor stream |
| GET | `/api/machine/<id>/sensor-health` | Sensor health status |
| GET | `/api/alerts` | 20 most recent alerts |

### Control API
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/machine/<id>/mode` | Set machine mode |
| POST | `/api/sensor/<id>/<type>/set-maintenance` | Individual sensor maintenance |
| POST | `/api/emergency-call/<id>` | Trigger emergency call |

### Chatbot API
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message to chatbot |
| GET | `/api/chat/suggestions` | Get suggested questions |
| GET | `/api/chat/history/<user_id>` | Chat history |

### Debug Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/debug/machines` | Machine status |
| GET | `/debug/test-email/<type>` | Test email (maintenance/sabotage) |
| GET | `/debug/test-call/<type>` | Test Twilio (emergency/maintenance/sms) |
| GET | `/debug/reset-email-flags` | Reset rate-limiting flags |
| GET | `/debug/fix-sample-data/<id>` | Generate sample chart data |

---

## 12. Frontend Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Bootstrap | 5.3.0 | Responsive UI framework |
| Font Awesome | 6.4.0 | Icon library |
| Chart.js | 4.4.0 | Real-time sensor charts |
| Chart.js Date Adapter | 3.0.0 | Time-series chart formatting |
| Plotly.js | latest | Interactive data visualization |
| AOS | 2.3.1 | Scroll animations (landing page) |
| Google Fonts (Inter) | - | Typography |

---

## 13. External Service Integrations

### Gmail SMTP
- Server: `smtp.gmail.com:587` with TLS
- Uses 16-character App Passwords (not account passwords)
- Async email sending via daemon threads
- Priority headers for critical alerts (`X-Priority: 1`)

### Twilio
- Voice calls with TwiML (Twilio Markup Language)
- SMS messaging
- Interactive call responses (key press acknowledgment)
- Call recording for documentation
- 30-second call timeout

### OpenAI (Optional)
- Configured but disabled by default
- Supports `gpt-*` models or local Ollama alternatives

---

## 14. Data Generation Pipeline

**`start_data_generation()`** runs as a background daemon thread:

1. Every **3 seconds**, iterates through all active (non-shutdown) machines
2. For each machine, generates values for all 4 sensors based on current mode
3. Runs anomaly detection on each reading
4. Saves readings to `sensor_readings` table
5. If anomalies detected:
   - **Maintenance mode**: Creates warning alert, sends email, triggers maintenance call
   - **Sabotage mode**: Creates critical alert, sends incident report email, triggers emergency calls + SMS backup
6. Status updates logged every 10 cycles (30 seconds)

---

## 15. Key Design Patterns

- **Rate Limiting**: Global sets prevent duplicate email/SMS alerts per machine
- **Flag Reset**: Rate-limit flags auto-clear when machine status changes
- **Thread Safety**: All external calls (email, Twilio) run in daemon threads
- **Async Operations**: Email and voice calls don't block the main Flask thread
- **Context-Aware Chatbot**: Queries live database for real-time machine context
- **Progressive Enhancement**: `ad.py` adds sensor health tracking on top of `app.py`'s core features

---

## 16. Configuration & Setup

### Dependencies
```
Flask
Flask-SQLAlchemy
twilio
openai
```

### Credentials Required
1. Gmail address + 16-char App Password
2. Twilio Account SID + Auth Token + Phone Number
3. Emergency contact phone numbers
4. (Optional) OpenAI API key

### Running
```bash
python app.py    # Standard version
python ad.py     # Advanced version with sensor health
```
Server starts on `http://localhost:5000`

---

## 17. Strengths

- Complete end-to-end pipeline: sensor simulation → anomaly detection → multi-channel alerting
- Real-time dashboard with 2-second refresh
- Professional email templates with incident timelines and forensic data
- Interactive AI chatbot with live database context
- Individual sensor health tracking with degradation modeling
- Rate limiting prevents notification spam
- Comprehensive REST API for external integrations
- Responsive UI across devices

---

## 18. Areas for Enhancement

- **ML Models**: Current anomaly detection is rule-based; could integrate Isolation Forest, LSTM, or Autoencoders
- **Persistent Chat History**: Currently in-memory only; could use database or Redis
- **Authentication**: No user auth system; currently open access
- **WebSocket/SSE**: Current polling (2s intervals); WebSockets would reduce overhead
- **Test Suite**: No automated tests present
- **Docker**: No containerization for deployment
- **Configuration Management**: Credentials hardcoded as placeholders; could use `.env` files
- **Data Retention**: No cleanup policy for old sensor readings

---

*Report generated by Joe Daniel A (2025)*
