"""Tests for F5 — Time-series rollups and retention.

Covers:
  - ReadingRollup model
  - rollup_readings() function
  - purge_old_readings() function
"""

import sys
import os
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

from app import (
    app, db, Machine, SensorReading, ReadingRollup,
    rollup_readings, purge_old_readings,
)


def _create_machine(session, name="Test Reactor"):
    m = Machine(name=name, machine_type="Chemical Reactor",
                description="Test", location="Lab", status="normal")
    session.add(m)
    session.commit()
    return m


def _create_readings(session, machine_id, count=10, minutes_ago=5):
    now = datetime.utcnow()
    for i in range(count):
        ts = now - timedelta(minutes=minutes_ago, seconds=count - i)
        sr = SensorReading(
            machine_id=machine_id, sensor_type="temperature",
            value=300.0 + i * 10, unit="C",
            is_anomaly=(i % 3 == 0), anomaly_score=0.1 + (i * 0.05),
            timestamp=ts,
        )
        session.add(sr)
    session.commit()


# ---------------------------------------------------------------------------
# ReadingRollup model
# ---------------------------------------------------------------------------
class TestReadingRollupModel:
    def test_create_rollup(self, db_session):
        m = _create_machine(db_session)
        now = datetime.utcnow()
        r = ReadingRollup(
            machine_id=m.id, sensor_type="temperature",
            interval="1min",
            window_start=now - timedelta(minutes=1),
            window_end=now,
            min_value=280.0, max_value=380.0, avg_value=330.0,
            count=10, anomaly_count=3,
        )
        db_session.add(r)
        db_session.commit()
        assert r.id is not None

    def test_to_dict(self, db_session):
        m = _create_machine(db_session)
        now = datetime.utcnow()
        r = ReadingRollup(
            machine_id=m.id, sensor_type="pressure",
            interval="1hour",
            window_start=now - timedelta(hours=1),
            window_end=now,
            min_value=10.0, max_value=25.0, avg_value=17.5,
            count=1200, anomaly_count=50,
        )
        db_session.add(r)
        db_session.commit()
        d = r.to_dict()
        assert d["interval"] == "1hour"
        assert d["count"] == 1200

    def test_unique_constraint(self, db_session):
        m = _create_machine(db_session)
        now = datetime.utcnow()
        window = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
        db_session.add(ReadingRollup(
            machine_id=m.id, sensor_type="temperature", interval="1min",
            window_start=window, window_end=window + timedelta(minutes=1),
            min_value=1, max_value=2, avg_value=1.5, count=1,
        ))
        db_session.commit()
        db_session.add(ReadingRollup(
            machine_id=m.id, sensor_type="temperature", interval="1min",
            window_start=window, window_end=window + timedelta(minutes=1),
            min_value=3, max_value=4, avg_value=3.5, count=1,
        ))
        import pytest
        with pytest.raises(Exception):
            db_session.commit()


# ---------------------------------------------------------------------------
# Rollup function
# ---------------------------------------------------------------------------
class TestRollupReadings:
    def test_rollup_creates_rows(self, db_session):
        m = _create_machine(db_session)
        _create_readings(db_session, m.id, count=20, minutes_ago=5)
        created = rollup_readings(interval='1min', lookback_minutes=10)
        assert created > 0

    def test_rollup_idempotent(self, db_session):
        m = _create_machine(db_session)
        _create_readings(db_session, m.id, count=10, minutes_ago=5)
        rollup_readings(interval='1min', lookback_minutes=10)
        count1 = ReadingRollup.query.count()
        rollup_readings(interval='1min', lookback_minutes=10)
        count2 = ReadingRollup.query.count()
        assert count1 == count2  # no duplicates


# ---------------------------------------------------------------------------
# Purge function
# ---------------------------------------------------------------------------
class TestPurgeReadings:
    def test_purge_removes_old_raw(self, db_session):
        m = _create_machine(db_session)
        old = datetime.utcnow() - timedelta(days=10)
        sr = SensorReading(
            machine_id=m.id, sensor_type="temperature",
            value=300.0, unit="C", timestamp=old,
        )
        db_session.add(sr)
        db_session.commit()
        result = purge_old_readings(raw_days=7)
        assert result['raw_deleted'] >= 1
        assert SensorReading.query.count() == 0

    def test_purge_keeps_recent(self, db_session):
        m = _create_machine(db_session)
        sr = SensorReading(
            machine_id=m.id, sensor_type="temperature",
            value=300.0, unit="C", timestamp=datetime.utcnow(),
        )
        db_session.add(sr)
        db_session.commit()
        purge_old_readings(raw_days=7)
        assert SensorReading.query.count() == 1


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
class TestRollupEndpoints:
    def test_rollups_endpoint_empty(self, client, db_session):
        m = _create_machine(db_session)
        resp = client.get(f'/api/machine/{m.id}/rollups')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['count'] == 0

    def test_rollups_endpoint_with_data(self, client, db_session):
        m = _create_machine(db_session)
        _create_readings(db_session, m.id, count=20, minutes_ago=5)
        # Trigger rollup via endpoint so it runs in the same request context
        client.post('/api/maintenance/rollups', json={
            'interval': '1min', 'lookback_minutes': 10, 'raw_days': 7,
        })
        resp = client.get(f'/api/machine/{m.id}/rollups?interval=1min&hours=1')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['count'] > 0

    def test_rollups_endpoint_404_unknown_machine(self, client, db_session):
        resp = client.get('/api/machine/999/rollups')
        data = resp.get_json()
        # get_or_404 raises 404, caught by except → 200 with error
        assert resp.status_code == 200
        assert data['success'] is False

    def test_trigger_rollups_endpoint(self, client, db_session):
        m = _create_machine(db_session)
        _create_readings(db_session, m.id, count=20, minutes_ago=5)
        resp = client.post('/api/maintenance/rollups', json={
            'interval': '1min', 'lookback_minutes': 10, 'raw_days': 7,
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['rollups_created'] > 0
