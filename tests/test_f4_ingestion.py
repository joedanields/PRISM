"""Tests for F4 — Real sensor ingestion (driver interface + pipeline).

Covers:
  - Reading dataclass validation
  - SimulatorDriver produces valid Reading objects
  - IngestionPipeline persists readings, handles quality, resolves tags
  - Integration: driver → pipeline → DB
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

from app import app, db, Machine, SensorReading, ReadingRollup
from ingestion.drivers import Reading
from ingestion.simulator import SimulatorDriver
from ingestion.pipeline import IngestionPipeline


def _create_machine(session, name="Test Reactor", machine_type="Chemical Reactor"):
    m = Machine(name=name, machine_type=machine_type,
                description="Test", location="Lab", status="normal")
    session.add(m)
    session.commit()
    return m


# ---------------------------------------------------------------------------
# Reading dataclass
# ---------------------------------------------------------------------------
class TestReadingDataclass:
    def test_valid_reading(self):
        r = Reading(
            machine_ref="1", sensor_type="temperature",
            value=350.0, unit="°C",
            timestamp=datetime.utcnow(), source="test",
        )
        assert r.quality == "good"
        assert r.is_anomaly is False

    def test_invalid_quality_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid quality"):
            Reading(
                machine_ref="1", sensor_type="temperature",
                value=350.0, unit="°C",
                timestamp=datetime.utcnow(), source="test",
                quality="invalid",
            )

    def test_nan_value_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid value"):
            Reading(
                machine_ref="1", sensor_type="temperature",
                value=float('nan'), unit="°C",
                timestamp=datetime.utcnow(), source="test",
            )

    def test_inf_value_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid value"):
            Reading(
                machine_ref="1", sensor_type="temperature",
                value=float('inf'), unit="°C",
                timestamp=datetime.utcnow(), source="test",
            )

    def test_uncertain_quality_valid(self):
        r = Reading(
            machine_ref="1", sensor_type="pressure",
            value=10.0, unit="bar",
            timestamp=datetime.utcnow(), source="modbus",
            quality="uncertain",
        )
        assert r.quality == "uncertain"


# ---------------------------------------------------------------------------
# SimulatorDriver
# ---------------------------------------------------------------------------
class TestSimulatorDriver:
    def test_connect_and_read(self, db_session):
        _create_machine(db_session)
        driver = SimulatorDriver()
        driver.connect()
        readings = list(driver.read())
        assert len(readings) > 0
        assert all(isinstance(r, Reading) for r in readings)
        assert all(r.source == "simulator" for r in readings)

    def test_read_requires_connect(self, db_session):
        _create_machine(db_session)
        driver = SimulatorDriver()
        import pytest
        with pytest.raises(RuntimeError, match="not connected"):
            list(driver.read())

    def test_read_returns_all_sensor_types(self, db_session):
        _create_machine(db_session, machine_type="Chemical Reactor")
        driver = SimulatorDriver()
        driver.connect()
        readings = list(driver.read())
        sensor_types = {r.sensor_type for r in readings}
        assert "temperature" in sensor_types
        assert "pressure" in sensor_types

    def test_close(self, db_session):
        driver = SimulatorDriver()
        driver.connect()
        driver.close()
        assert not driver._connected


# ---------------------------------------------------------------------------
# IngestionPipeline
# ---------------------------------------------------------------------------
class TestIngestionPipeline:
    def test_ingest_persists_readings(self, db_session):
        m = _create_machine(db_session)
        pipeline = IngestionPipeline()
        readings = [Reading(
            machine_ref=str(m.id), sensor_type="temperature",
            value=350.0, unit="°C", timestamp=datetime.utcnow(),
            source="test",
        )]
        stats = pipeline.ingest(readings)
        assert stats["ingested"] == 1
        assert SensorReading.query.count() == 1

    def test_ingest_sets_source(self, db_session):
        m = _create_machine(db_session)
        pipeline = IngestionPipeline()
        readings = [Reading(
            machine_ref=str(m.id), sensor_type="temperature",
            value=350.0, unit="°C", timestamp=datetime.utcnow(),
            source="mqtt",
        )]
        pipeline.ingest(readings)
        sr = SensorReading.query.first()
        assert sr.source == "mqtt"

    def test_reject_bad_quality(self, db_session):
        m = _create_machine(db_session)
        pipeline = IngestionPipeline(reject_bad_quality=True)
        readings = [Reading(
            machine_ref=str(m.id), sensor_type="temperature",
            value=350.0, unit="°C", timestamp=datetime.utcnow(),
            source="test", quality="bad",
        )]
        stats = pipeline.ingest(readings)
        assert stats["skipped_quality"] == 1
        assert stats["ingested"] == 0
        assert SensorReading.query.count() == 0

    def test_accept_uncertain_quality(self, db_session):
        m = _create_machine(db_session)
        pipeline = IngestionPipeline(reject_bad_quality=True)
        readings = [Reading(
            machine_ref=str(m.id), sensor_type="temperature",
            value=350.0, unit="°C", timestamp=datetime.utcnow(),
            source="opcua", quality="uncertain",
        )]
        stats = pipeline.ingest(readings)
        assert stats["ingested"] == 1

    def test_tag_map_resolution(self, db_session):
        m = _create_machine(db_session)
        pipeline = IngestionPipeline(tag_map={"TEMP_001": m.id})
        readings = [Reading(
            machine_ref="TEMP_001", sensor_type="temperature",
            value=350.0, unit="°C", timestamp=datetime.utcnow(),
            source="mqtt",
        )]
        stats = pipeline.ingest(readings)
        assert stats["ingested"] == 1
        assert SensorReading.query.first().machine_id == m.id

    def test_unknown_machine_ref(self, db_session):
        pipeline = IngestionPipeline()
        readings = [Reading(
            machine_ref="NONEXISTENT", sensor_type="temperature",
            value=350.0, unit="°C", timestamp=datetime.utcnow(),
            source="test",
        )]
        stats = pipeline.ingest(readings)
        assert stats["errors"] == 1

    def test_stats_tracking(self, db_session):
        m = _create_machine(db_session)
        pipeline = IngestionPipeline()
        readings = [
            Reading(machine_ref=str(m.id), sensor_type="temperature",
                    value=350.0, unit="°C", timestamp=datetime.utcnow(), source="test"),
            Reading(machine_ref=str(m.id), sensor_type="pressure",
                    value=20.0, unit="bar", timestamp=datetime.utcnow(), source="test"),
        ]
        pipeline.ingest(readings)
        stats = pipeline.get_stats()
        assert stats["ingested"] == 2


# ---------------------------------------------------------------------------
# Integration: driver → pipeline → DB
# ---------------------------------------------------------------------------
class TestDriverPipelineIntegration:
    def test_full_pipeline(self, db_session):
        m = _create_machine(db_session)
        driver = SimulatorDriver()
        driver.connect()
        pipeline = IngestionPipeline()
        readings = list(driver.read())
        stats = pipeline.ingest(readings)
        assert stats["ingested"] > 0
        assert SensorReading.query.count() == stats["ingested"]

    def test_anomaly_readings_have_high_score(self, db_session):
        m = _create_machine(db_session, machine_type="Chemical Reactor")
        m.status = "sabotage"
        db_session.commit()
        driver = SimulatorDriver()
        driver.connect()
        pipeline = IngestionPipeline()
        readings = list(driver.read())
        pipeline.ingest(readings)
        anomalies = SensorReading.query.filter_by(is_anomaly=True).all()
        for a in anomalies:
            assert a.anomaly_score >= 0.8
