"""Characterization tests for the alerting system.

Captures current behaviour of alert creation and rate-limiting globals
so the F1 refactor can be verified against these contracts.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("EMAIL_USER", "t@t.com")
os.environ.setdefault("EMAIL_PASSWORD", "x")
os.environ.setdefault("EMAIL_MAINTENANCE_TEAM", "t@t.com")
os.environ.setdefault("EMAIL_PLANT_MANAGER", "t@t.com")
os.environ.setdefault("EMAIL_EMERGENCY_RESPONSE", "t@t.com")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "00000000000000000000000000000000")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("TWILIO_EMERGENCY_CONTACTS", "+15550000001")

from app import app, db, Machine, SensorReading, Alert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _create_machine(session, name="Test Reactor", status="normal"):
    m = Machine(
        name=name,
        machine_type="Chemical Reactor",
        description="Test machine",
        location="Test Lab",
        status=status,
    )
    session.add(m)
    session.commit()
    return m


def _create_reading(session, machine_id, sensor_type="temperature",
                    value=300.0, is_anomaly=False, anomaly_score=0.0):
    r = SensorReading(
        machine_id=machine_id,
        sensor_type=sensor_type,
        value=value,
        unit="°C",
        is_anomaly=is_anomaly,
        anomaly_score=anomaly_score,
    )
    session.add(r)
    session.commit()
    return r


# ---------------------------------------------------------------------------
# Alert model tests
# ---------------------------------------------------------------------------
class TestAlertModel:
    """Verify Alert model fields and serialization."""

    def test_create_alert(self, db_session):
        m = _create_machine(db_session)
        alert = Alert(
            machine_id=m.id,
            alert_type="warning",
            severity="medium",
            title="Test Alert",
            message="Something happened",
            sensor_data='{"temperature": 450}',
        )
        db_session.add(alert)
        db_session.commit()

        loaded = Alert.query.get(alert.id)
        assert loaded is not None
        assert loaded.alert_type == "warning"
        assert loaded.severity == "medium"
        assert loaded.is_acknowledged is False
        assert loaded.email_sent is False
        assert loaded.sms_sent is False
        assert loaded.created_at is not None

    def test_to_dict(self, db_session):
        m = _create_machine(db_session)
        alert = Alert(
            machine_id=m.id,
            alert_type="critical",
            severity="high",
            title="Critical Test",
            message="Bad",
        )
        db_session.add(alert)
        db_session.commit()

        d = alert.to_dict()
        assert d["alert_type"] == "critical"
        assert d["severity"] == "high"
        assert d["is_acknowledged"] is False
        assert d["sensor_data"] is None  # no JSON passed

    def test_sensor_data_json_roundtrip(self, db_session):
        m = _create_machine(db_session)
        import json
        data = json.dumps({"temperature": 730, "pressure": 48})
        alert = Alert(
            machine_id=m.id,
            alert_type="critical",
            severity="critical",
            title="JSON test",
            message="test",
            sensor_data=data,
        )
        db_session.add(alert)
        db_session.commit()

        d = alert.to_dict()
        assert d["sensor_data"]["temperature"] == 730
        assert d["sensor_data"]["pressure"] == 48


# ---------------------------------------------------------------------------
# Machine model tests
# ---------------------------------------------------------------------------
class TestMachineModel:
    def test_create_machine(self, db_session):
        m = _create_machine(db_session)
        assert m.id is not None
        assert m.status == "normal"
        assert m.is_active is True

    def test_to_dict(self, db_session):
        m = _create_machine(db_session, name="Test Fermenter")
        d = m.to_dict()
        assert d["name"] == "Test Fermenter"
        assert d["machine_type"] == "Biotech Fermenter" or d["machine_type"] == "Chemical Reactor"
        assert d["status"] == "normal"


# ---------------------------------------------------------------------------
# SensorReading model tests
# ---------------------------------------------------------------------------
class TestSensorReadingModel:
    def test_create_reading(self, db_session):
        m = _create_machine(db_session)
        r = _create_reading(db_session, m.id, value=350.0, is_anomaly=True, anomaly_score=0.6)
        assert r.id is not None
        assert r.value == 350.0
        assert r.is_anomaly is True

    def test_to_dict(self, db_session):
        m = _create_machine(db_session)
        r = _create_reading(db_session, m.id, sensor_type="pressure", value=25.0)
        d = r.to_dict()
        assert d["sensor_type"] == "pressure"
        assert d["value"] == 25.0
        assert d["unit"] == "°C"  # default in helper


# ---------------------------------------------------------------------------
# Rate-limiting globals tests (characterize current in-memory sets)
# ---------------------------------------------------------------------------
class TestRateLimitingGlobals:
    """Verify the global rate-limiting sets exist and behave as expected."""

    def test_sets_are_importable(self):
        from app import sent_maintenance_emails, sent_sabotage_emails, sent_twilio_calls
        assert isinstance(sent_maintenance_emails, set)
        assert isinstance(sent_sabotage_emails, set)
        assert isinstance(sent_twilio_calls, set)

    def test_set_mutation(self):
        """Adding to and clearing the sets works (current in-memory behaviour)."""
        from app import sent_maintenance_emails
        sentinel = "machine_999"
        sent_maintenance_emails.add(sentinel)
        assert sentinel in sent_maintenance_emails
        sent_maintenance_emails.discard(sentinel)
        assert sentinel not in sent_maintenance_emails


# ---------------------------------------------------------------------------
# Interim lockdown tests (Phase 0 config guards)
# ---------------------------------------------------------------------------
class TestInterimLockdown:
    """Verify debug/money endpoints return 404 when flags are off."""

    def test_debug_machines_blocked_by_default(self, client):
        """ENABLE_DEBUG_ROUTES defaults to false in .env.example."""
        from app import config as _cfg
        original = _cfg.ENABLE_DEBUG_ROUTES
        _cfg.ENABLE_DEBUG_ROUTES = False
        try:
            resp = client.get("/debug/machines")
            assert resp.status_code == 404
        finally:
            _cfg.ENABLE_DEBUG_ROUTES = original

    def test_emergency_call_blocked_by_default(self, client):
        from app import config as _cfg
        original = _cfg.ENABLE_EMERGENCY_ENDPOINTS
        _cfg.ENABLE_EMERGENCY_ENDPOINTS = False
        try:
            resp = client.get("/api/emergency-call/1")
            assert resp.status_code in (401, 404)
        finally:
            _cfg.ENABLE_EMERGENCY_ENDPOINTS = original

    def test_debug_machines_allowed_when_enabled(self, client):
        from app import config as _cfg
        original = _cfg.ENABLE_DEBUG_ROUTES
        _cfg.ENABLE_DEBUG_ROUTES = True
        try:
            resp = client.get("/debug/machines")
            assert resp.status_code == 200
        finally:
            _cfg.ENABLE_DEBUG_ROUTES = original
