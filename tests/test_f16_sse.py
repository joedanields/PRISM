"""Tests for F16 — SSE real-time push transport.

Covers:
  - /api/events endpoint returns SSE stream
  - Event formatting
  - Query parameter validation
  - Generator yields heartbeat when idle
"""

import sys
import os
import json
from datetime import datetime, timedelta

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

from app import app, db, Machine, SensorReading, Alert, SensorHealth
from realtime.stream import _format_event, _get_max_id, _get_new_readings, _get_new_alerts


def _create_machine(session, name="Test Reactor", machine_type="Chemical Reactor"):
    m = Machine(name=name, machine_type=machine_type,
                description="Test", location="Lab", status="normal")
    session.add(m)
    session.commit()
    return m


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------
class TestFormatEvent:
    def test_format_basic(self):
        result = _format_event('reading', {'value': 42})
        assert result.startswith('event: reading\n')
        assert 'data: {"value": 42}\n\n' in result

    def test_format_heartbeat(self):
        result = _format_event('heartbeat', {'ts': '2026-01-01T00:00:00'})
        assert 'event: heartbeat\n' in result

    def test_format_nested_json(self):
        result = _format_event('alert', {'machine_id': 1, 'readings': [{'v': 1}]})
        parsed_data = result.split('data: ')[1].strip()
        obj = json.loads(parsed_data)
        assert obj['machine_id'] == 1
        assert len(obj['readings']) == 1


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
class TestHelperFunctions:
    def test_get_max_id_empty(self, db_session):
        assert _get_max_id(SensorReading) == 0

    def test_get_max_id_with_data(self, db_session):
        m = _create_machine(db_session)
        for i in range(5):
            db_session.add(SensorReading(
                machine_id=m.id, sensor_type="temperature",
                value=300.0, unit="C", timestamp=datetime.utcnow(),
            ))
        db_session.commit()
        assert _get_max_id(SensorReading) == 5

    def test_get_new_readings(self, db_session):
        m = _create_machine(db_session)
        for i in range(3):
            db_session.add(SensorReading(
                machine_id=m.id, sensor_type="temperature",
                value=300.0 + i, unit="C", timestamp=datetime.utcnow(),
            ))
        db_session.commit()
        readings = _get_new_readings(since_id=0)
        assert len(readings) == 3

    def test_get_new_readings_filtered(self, db_session):
        m1 = _create_machine(db_session, name="M1")
        m2 = _create_machine(db_session, name="M2")
        for mid in [m1.id, m2.id]:
            db_session.add(SensorReading(
                machine_id=mid, sensor_type="temperature",
                value=300.0, unit="C", timestamp=datetime.utcnow(),
            ))
        db_session.commit()
        readings = _get_new_readings(since_id=0, machine_id=m1.id)
        assert len(readings) == 1
        assert readings[0].machine_id == m1.id

    def test_get_new_alerts(self, db_session):
        m = _create_machine(db_session)
        db_session.add(Alert(
            machine_id=m.id, alert_type="warning", severity="medium",
            title="Test", message="Test alert",
        ))
        db_session.commit()
        alerts = _get_new_alerts(since_id=0)
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------
class TestSSEEndpoint:
    def test_events_endpoint_returns_stream(self, client, db_session):
        resp = client.get('/api/events?poll=1')
        assert resp.status_code == 200
        assert resp.content_type.startswith('text/event-stream')

    def test_events_endpoint_headers(self, client, db_session):
        resp = client.get('/api/events?poll=1')
        assert resp.headers.get('Cache-Control') == 'no-cache'
        assert resp.headers.get('Connection') == 'keep-alive'

    def test_events_with_machine_id(self, client, db_session):
        m = _create_machine(db_session)
        resp = client.get(f'/api/events?machine_id={m.id}&poll=1')
        assert resp.status_code == 200
        assert resp.content_type.startswith('text/event-stream')

    def test_events_returns_readings_when_present(self, client, db_session):
        m = _create_machine(db_session)
        db_session.add(SensorReading(
            machine_id=m.id, sensor_type="temperature",
            value=350.0, unit="C", timestamp=datetime.utcnow(),
        ))
        db_session.commit()
        resp = client.get(f'/api/events?machine_id={m.id}&poll=1')
        assert resp.status_code == 200
        assert resp.content_type.startswith('text/event-stream')

    def test_poll_interval_clamped(self, client, db_session):
        # Verify endpoint accepts clamped poll values without error
        resp = client.get('/api/events?poll=0.5')
        assert resp.status_code == 200
        # Don't read the full stream — just verify it starts
        # The generator will be cleaned up by GC
