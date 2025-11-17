# PRISM: Predictive Industrial Safety & Monitoring AI

PRISM is a comprehensive, AI-driven predictive maintenance and safety monitoring system for industrial environments. It simulates real-time sensor data from various industrial machines, detects anomalies, and triggers intelligent alerts, including detailed emails, emergency calls, and SMS notifications. The system also features an AI-powered chatbot for interactive diagnostics and operational support.

## Key Features

- **Real-time Machine Simulation**: Generates continuous sensor data for four distinct types of industrial machines.
- **Multiple Machine Modes**: Supports different operational modes for each machine, including `normal`, `maintenance`, and `sabotage`, each with unique data generation patterns.
- **Advanced Anomaly Detection**: Implements a rule-based system to detect deviations from normal operating parameters and calculates an anomaly score.
- **Intelligent Alerting System**:
    - **Email Alerts**: Sends professionally formatted HTML emails for maintenance requests and critical sabotage incidents.
    - **Voice Calls & SMS**: Uses Twilio to make automated emergency calls and send SMS backup alerts to key personnel.
- **AI-Powered Chatbot**: An integrated chatbot (`MaintenanceBot`) that assists with:
    - Equipment diagnostics and troubleshooting.
    - Real-time status checks.
    - Safety protocols and maintenance advice.
- **Web-Based Dashboard**: A Flask-based web interface to visualize machine status, sensor readings, and recent alerts.
- **Sensor Health Tracking**: Monitors and simulates the degradation of sensor health over time, adding another layer of predictive maintenance.
- **Comprehensive API**: Offers a rich set of API endpoints for interacting with the system, fetching data, and triggering actions.

## Monitored Machines

The simulation includes four pre-configured industrial machines, each with a unique set of sensors:

1.  **Chemical Reactor (R-001)**:
    -   Sensors: Temperature, Pressure, Flow Rate, Level.
2.  **Biotech Fermenter (F-003)**:
    -   Sensors: Temperature, pH, Dissolved Oxygen, Agitation.
3.  **Distillation Column (D-002)**:
    -   Sensors: Top Temperature, Bottom Temperature, Pressure, Reflux Ratio.
4.  **Heat Exchanger (HX-005)**:
    -   Sensors: Inlet Temperature, Outlet Temperature, Pressure Drop, Flow Rate.

## Setup and Installation

### Prerequisites

-   Python 3.7+
-   Flask and other Python packages (installable via `pip`).
-   A Gmail account (for sending email alerts).
-   A Twilio account (for making calls and sending SMS).

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Install Dependencies

It is recommended to use a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
pip install Flask Flask-SQLAlchemy twilio openai
```

### 3. Configure Credentials

You need to replace the placeholder credentials in `app.py` and/or `ad.py` with your actual service credentials.

#### Email Configuration (Gmail)

In the `EmailConfig` class, replace the `$$` placeholders:

```python
class EmailConfig:
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    EMAIL_USER = 'your-email@gmail.com'  # Your Gmail address
    EMAIL_PASSWORD = 'your-16-char-app-password'  # Gmail App Password
    MAINTENANCE_TEAM = 'maintenance-team-email@example.com'
    PLANT_MANAGER = 'plant-manager-email@example.com'
    EMERGENCY_RESPONSE = 'emergency-response-email@example.com'
```

**Note**: You must generate a 16-character "App Password" from your Google Account settings for `EMAIL_PASSWORD`. Your regular Google password will not work.

#### Twilio Configuration

In the `TwilioConfig` class, replace the `$$`, `%%`, and `@@` placeholders:

```python
class TwilioConfig:
    ACCOUNT_SID = 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'  # Your Twilio Account SID
    AUTH_TOKEN = 'your_twilio_auth_token'          # Your Twilio Auth Token
    TWILIO_PHONE_NUMBER = '+1234567890'           # Your Twilio Phone Number
    EMERGENCY_CONTACTS = [
        '+19876543210',  # Plant Manager's number
        '+19876543211',  # Maintenance Chief's number
    ]
```

## Running the Application

To start the system, run the `app.py` or `ad.py` file:

```bash
python app.py
```

Or, for the advanced version:

```bash
python ad.py
```

The application will start, create the necessary database (`machines.db`), and begin generating sensor data in the background.

You can access the web interface at:
-   **Landing Page**: `http://localhost:5000/`
-   **Dashboard**: `http://localhost:5000/dashboard`
-   **AI Chatbot**: `http://localhost:5000/chat`

## API and Debug Endpoints

The application exposes several API and debug endpoints to interact with the system programmatically.

### Main API Endpoints

-   `GET /api/machines`: Retrieve data for all active machines.
-   `GET /api/machine/<id>/latest`: Get the latest sensor readings for a specific machine.
-   `POST /api/machine/<id>/mode`: Set the operational mode (`normal`, `maintenance`, `sabotage`) for a machine.
-   `GET /api/alerts`: Fetch the 20 most recent alerts.
-   `POST /api/chat`: Interact with the AI chatbot.
-   `GET /api/machine/<id>/chart-data`: Get historical data formatted for charts.
-   `GET /api/machine/<id>/sensor-health`: Get the health status of all sensors on a machine.
-   `POST /api/emergency-call/<id>`: Manually trigger an emergency call for a machine.
