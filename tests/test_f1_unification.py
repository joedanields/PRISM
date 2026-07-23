"""Tests for F1 — Unified codebase (app.py after ad.py merge).

Covers:
  - SensorHealth model
  - SensorHealthTracker
  - initialize_all_sensor_health()
  - Key unified routes (sensor-health, historical-data, live-stream, set-maintenance)
"""

import sys
import os
import json

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

from app import (
    app, db, Machine, SensorReading, Alert, SensorHealth,
    SensorHealthTracker, sensor_health_tracker, MACHINES_CONFIG,
    initialize_all_sensor_health,
)


def _create_machine(session, name="Test Reactor", machine_type="Chemical Reactor",
                    status="normal"):
    m = Machine(
        name=name, machine_type=machine_type,
        description="Test", location="Lab", status=status,
    )
    session.add(m)
    session.commit()
    return m


# ---------------------------------------------------------------------------
# SensorHealth model
# ---------------------------------------------------------------------------
class TestSensorHealthModel:
    def test_create_sensor_health(self, db_session):
        m = _create_machine(db_session)
        sh = SensorHealth(
            machine_id=m.id, sensor_type="temperature",
            health_percentage=95.0, status="healthy",
        )
        db_session.add(sh)
        db_session.commit()
        assert sh.id is not None
        assert sh.health_percentage == 95.0
        assert sh.status == "healthy"
        assert sh.last_updated is not None

    def test_unique_constraint(self, db_session):
        m = _create_machine(db_session)
        db_session.add(SensorHealth(machine_id=m.id, sensor_type="pressure", health_percentage=100.0))
        db_session.commit()
        db_session.add(SensorHealth(machine_id=m.id, sensor_type="pressure", health_percentage=90.0))
        import pytest
        with pytest.raises(Exception):
            db_session.commit()

    def test_to_dict(self, db_session):
        m = _create_machine(db_session)
        sh = SensorHealth(machine_id=m.id, sensor_type="ph", health_percentage=78.5, status="warning")
        db_session.add(sh)
        db_session.commit()
        d = sh.to_dict()
        assert d["sensor_type"] == "ph"
        assert d["health_percentage"] == 78.5
        assert d["status"] == "warning"


# ---------------------------------------------------------------------------
# SensorHealthTracker
# ---------------------------------------------------------------------------
class TestSensorHealthTracker:
    def test_initialize_sensor_health(self, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "temperature")
        sh = SensorHealth.query.filter_by(machine_id=m.id, sensor_type="temperature").first()
        assert sh is not None
        assert sh.health_percentage == 100.0

    def test_degradation(self, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "pressure")
        health, status = sensor_health_tracker.get_sensor_health(m.id, "pressure")
        # Immediately after init, health should still be ~100
        assert health <= 100.0

    def test_set_maintenance_mode(self, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "flow_rate")
        health = sensor_health_tracker.set_maintenance_mode(m.id, "flow_rate")
        assert 30.0 <= health <= 50.0

    def test_get_all_machine_sensor_health(self, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "temperature")
        sensor_health_tracker.initialize_sensor_health(m.id, "pressure")
        all_health = sensor_health_tracker.get_all_machine_sensor_health(m.id)
        # Returns health for ALL configured sensors on this machine type
        assert len(all_health) >= 2
        assert "temperature" in all_health
        assert "pressure" in all_health


# ---------------------------------------------------------------------------
# initialize_all_sensor_health
# ---------------------------------------------------------------------------
class TestInitializeAllSensorHealth:
    def test_initializes_all_sensors(self, db_session):
        m = _create_machine(db_session, name="R-001", machine_type="Chemical Reactor")
        initialize_all_sensor_health()
        config = MACHINES_CONFIG.get("Chemical Reactor", {})
        expected_sensors = list(config.get("sensors", {}).keys())
        assert len(expected_sensors) > 0
        for st in expected_sensors:
            sh = SensorHealth.query.filter_by(machine_id=m.id, sensor_type=st).first()
            assert sh is not None, f"SensorHealth missing for {st}"


# ---------------------------------------------------------------------------
# Unified routes (basic characterization)
# ---------------------------------------------------------------------------
class TestUnifiedRoutes:
    def test_api_machines_returns_200(self, client):
        resp = client.get("/api/machines")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_sensor_health_route(self, client, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "temperature")
        resp = client.get(f"/api/machine/{m.id}/sensor-health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "sensor_health" in data

    def test_live_stream_route(self, client, db_session):
        m = _create_machine(db_session)
        from datetime import datetime
        sr = SensorReading(
            machine_id=m.id, sensor_type="temperature",
            value=350.0, unit="C", is_anomaly=False, anomaly_score=0.1,
        )
        db_session.add(sr)
        db_session.commit()
        resp = client.get(f"/api/machine/{m.id}/live-stream")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_historical_data_route(self, client, db_session):
        m = _create_machine(db_session)
        resp = client.get(f"/api/machine/{m.id}/historical-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_set_maintenance_route(self, client, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "ph")
        resp = client.post(
            f"/api/sensor/{m.id}/ph/set-maintenance",
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert 30.0 <= data["sensor_health"] <= 50.0

    def test_backward_compat_maintenance_url(self, client, db_session):
        m = _create_machine(db_session)
        sensor_health_tracker.initialize_sensor_health(m.id, "ph")
        resp = client.post(
            f"/api/sensor/{m.id}/ph/maintenance",
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_chart_data_simple_route(self, client, db_session):
        m = _create_machine(db_session)
        resp = client.get(f"/api/machine/{m.id}/chart-data-simple")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
