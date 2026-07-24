"""Tests for F6: Historical replay & scenario engine.

Covers ReplayDriver, ScenarioEngine, scenario file I/O, and API endpoints.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app, db, Machine, User
from app import SensorReading


@pytest.fixture()
def app_obj():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_obj):
    return app_obj.test_client()


@pytest.fixture()
def db_session(app_obj):
    with app_obj.app_context():
        yield db.session


def _seed_machine():
    m = Machine(name='Test Reactor', machine_type='Chemical Reactor',
                description='Test', location='Lab', status='normal')
    db.session.add(m)
    db.session.commit()
    return m


def _login_admin(client):
    from werkzeug.security import generate_password_hash
    u = User(username='admin', email='admin@test.com', role='admin',
             password_hash=generate_password_hash('pass123'))
    db.session.add(u)
    db.session.commit()
    client.post('/login', data={'username': 'admin', 'password': 'pass123'}, follow_redirects=True)


@pytest.fixture
def sample_readings(app_obj):
    with app.app_context():
        base = datetime(2026, 1, 1, 12, 0, 0)
        for i in range(30):
            db.session.add(SensorReading(
                machine_id=1,
                sensor_type='temperature',
                value=320.0 + i * 0.5,
                unit='°C',
                timestamp=base + timedelta(minutes=i),
                is_anomaly=(i > 25),
                source='simulator',
                quality='good',
            ))
        db.session.commit()


# ---------------------------------------------------------------------------
# ReplayDriver
# ---------------------------------------------------------------------------

class TestReplayDriver:
    def test_connect_and_count(self, app_obj):
        with app.app_context():
            _seed_machine()
            base = datetime(2026, 1, 1, 12, 0, 0)
            for i in range(30):
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='temperature', value=320.0 + i * 0.5,
                    unit='°C', timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
            db.session.commit()

            start = datetime(2026, 1, 1, 12, 0, 0)
            end = datetime(2026, 1, 1, 12, 30, 0)
            from ingestion.replay import ReplayDriver
            driver = ReplayDriver(start, end)
            driver.connect()
            assert driver.total_readings == 30
            assert driver.progress == 0.0

    def test_read_empty_when_cursor_at_end(self, app_obj):
        with app.app_context():
            _seed_machine()
        with app.app_context():
            db.session.add(SensorReading(
                machine_id=1, sensor_type='temperature', value=320.0,
                unit='°C', timestamp=datetime(2026, 1, 1, 12, 0, 0),
                source='simulator', quality='good'))
            db.session.commit()
            from ingestion.replay import ReplayDriver
            driver = ReplayDriver(datetime(2026, 1, 1), datetime(2026, 1, 2), speed=1000.0)
            driver.connect()
            while driver.progress < 1.0:
                driver.read()
            batch = driver.read()
            assert batch == [] or len(batch) == 0

    def test_read_returns_readings(self, app_obj):
        with app.app_context():
            _seed_machine()
        with app.app_context():
            base = datetime(2026, 1, 1, 12, 0, 0)
            for i in range(30):
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='temperature', value=320.0 + i,
                    unit='°C', timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
            db.session.commit()
            from ingestion.replay import ReplayDriver
            driver = ReplayDriver(datetime(2026, 1, 1, 12, 0, 0), datetime(2026, 1, 1, 12, 30, 0), speed=10000.0)
            driver.connect()
            batch = driver.read()
            assert len(batch) > 0
            assert batch[0].source.startswith('replay(')

    def test_machine_filter(self, app_obj):
        with app.app_context():
            _seed_machine()
        with app.app_context():
            base = datetime(2026, 1, 1, 12, 0, 0)
            for i in range(10):
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='temperature', value=320.0,
                    unit='°C', timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
            db.session.commit()
            from ingestion.replay import ReplayDriver
            driver = ReplayDriver(datetime(2026, 1, 1), datetime(2026, 1, 2), machine_id=1)
            driver.connect()
            assert driver.total_readings == 10

    def test_machine_filter_no_match(self, app_obj):
        with app.app_context():
            from ingestion.replay import ReplayDriver
            driver = ReplayDriver(datetime(2026, 1, 1), datetime(2026, 1, 2), machine_id=999)
            driver.connect()
            assert driver.total_readings == 0

    def test_speed_clamping(self):
        from ingestion.replay import ReplayDriver
        driver = ReplayDriver(datetime.now(), datetime.now(), speed=0.01)
        assert driver.speed == 0.1
        driver2 = ReplayDriver(datetime.now(), datetime.now(), speed=999)
        assert driver2.speed == 100.0

    def test_close(self, app_obj):
        with app.app_context():
            from ingestion.replay import ReplayDriver
            driver = ReplayDriver(datetime.now(), datetime.now())
            driver.connect()
            assert driver._connected
            driver.close()
            assert not driver._connected


# ---------------------------------------------------------------------------
# ScenarioEngine
# ---------------------------------------------------------------------------

class TestScenarioEngine:
    def _make_scenario(self):
        from ingestion.replay import Scenario, ScenarioStep
        return Scenario(
            name='test_drift',
            description='Test sensor drift',
            version='1.0',
            duration_seconds=60,
            steps=[ScenarioStep(0, 'Chemical Reactor', 'temperature', 'sensor_drift',
                                {'drift_rate': 2.0, 'duration_seconds': 60})],
            target_machine_id=1,
        )

    def test_generate_batch(self):
        from ingestion.replay import ScenarioEngine
        engine = ScenarioEngine(self._make_scenario())
        engine.start()
        readings = engine.generate_batch(30)
        assert len(readings) > 0
        assert all(r.source.startswith('scenario:test_drift') for r in readings)

    def test_bearing_degradation(self):
        from ingestion.replay import ScenarioEngine, Scenario, ScenarioStep
        scenario = Scenario(
            name='bearing_test', description='', version='1.0', duration_seconds=100,
            steps=[ScenarioStep(0, 'Chemical Reactor', 'temperature', 'bearing_degradation',
                                {'degradation_rate': 0.5, 'duration_seconds': 100})],
            target_machine_id=1,
        )
        engine = ScenarioEngine(scenario)
        engine.start()
        early = engine.generate_batch(10)
        late = engine.generate_batch(90)
        assert len(early) > 0
        assert len(late) > 0

    def test_sudden_spike(self):
        from ingestion.replay import ScenarioEngine, Scenario, ScenarioStep
        scenario = Scenario(
            name='spike_test', description='', version='1.0', duration_seconds=60,
            steps=[ScenarioStep(0, 'Chemical Reactor', 'temperature', 'sudden_spike',
                                {'spike_multiplier': 2.5, 'spike_duration': 5})],
            target_machine_id=1,
        )
        engine = ScenarioEngine(scenario)
        engine.start()
        during = engine.generate_batch(3)
        assert len(during) > 0
        after = engine.generate_batch(10)
        assert len(after) > 0

    def test_stuck_at(self):
        from ingestion.replay import ScenarioEngine, Scenario, ScenarioStep
        scenario = Scenario(
            name='stuck_test', description='', version='1.0', duration_seconds=120,
            steps=[ScenarioStep(10, 'Chemical Reactor', 'temperature', 'stuck_at',
                                {'freeze_duration': 60})],
            target_machine_id=1,
        )
        engine = ScenarioEngine(scenario)
        engine.start()
        before = engine.generate_batch(5)
        during = engine.generate_batch(30)
        assert len(during) > 0


# ---------------------------------------------------------------------------
# Scenario file I/O
# ---------------------------------------------------------------------------

class TestScenarioIO:
    def test_save_and_load(self, tmp_path):
        from ingestion.replay import Scenario, ScenarioStep, save_scenario, load_scenario
        scenario = Scenario(
            name='test_save', description='Save test', version='1.0', duration_seconds=60,
            steps=[ScenarioStep(0, 'Chemical Reactor', 'temperature', 'sensor_drift',
                                {'drift_rate': 1.0, 'duration_seconds': 60})],
        )
        path = str(tmp_path / 'test_save.json')
        save_scenario(scenario, path)
        loaded = load_scenario(path)
        assert loaded.name == 'test_save'
        assert loaded.duration_seconds == 60
        assert len(loaded.steps) == 1
        assert loaded.steps[0].fault_pattern == 'sensor_drift'

    def test_list_scenarios(self, tmp_path):
        from ingestion.replay import Scenario, save_scenario, list_scenarios
        for name in ['a', 'b', 'c']:
            s = Scenario(name=name, description='', version='1.0', duration_seconds=30, steps=[])
            save_scenario(s, str(tmp_path / f'{name}.json'))
        files = list_scenarios(str(tmp_path))
        assert files == ['a.json', 'b.json', 'c.json']

    def test_list_scenarios_empty(self, tmp_path):
        from ingestion.replay import list_scenarios
        files = list_scenarios(str(tmp_path / 'nonexistent'))
        assert files == []


# ---------------------------------------------------------------------------
# Fault patterns
# ---------------------------------------------------------------------------

class TestFaultPatterns:
    def test_all_patterns_exist(self):
        from ingestion.replay import FAULT_PATTERNS
        for name in ['sensor_drift', 'sudden_spike', 'stuck_at', 'bearing_degradation', 'intermittent_fault']:
            assert name in FAULT_PATTERNS

    def test_all_patterns_have_params(self):
        from ingestion.replay import FAULT_PATTERNS
        for name, pattern in FAULT_PATTERNS.items():
            assert 'description' in pattern
            assert 'params' in pattern


# ---------------------------------------------------------------------------
# API endpoints (require auth)
# ---------------------------------------------------------------------------

class TestReplayAPI:
    def test_list_scenarios_endpoint(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/scenarios')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']

    def test_get_scenario_not_found(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/scenario/nonexistent')
        assert resp.status_code == 404

    def test_start_replay_missing_params(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/replay', json={})
        assert resp.status_code == 400

    def test_start_replay_empty_window(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/replay', json={
            'start': '2026-01-01T00:00:00',
            'end': '2026-01-01T00:01:00',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']
        assert data['total_readings'] == 0

    def test_run_scenario_missing_file(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/scenario/nonexistent/run', json={})
        assert resp.status_code == 404

    def test_train_ml_no_machine(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/ml/train', json={})
        assert resp.status_code == 400
        assert 'machine_id' in resp.get_json()['error']

    def test_train_ml_no_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/ml/train', json={'machine_id': 1})
        assert resp.status_code == 400

    def test_ml_status(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/ml/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']
        assert 'Chemical Reactor' in data['models']
