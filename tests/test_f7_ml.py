"""Tests for F7: ML anomaly detection.

Covers Detection contract, IsolationForestDetector, HybridDetector, and API endpoints.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app, db, Machine, User, SensorReading
from detection.ml import (
    Detection, IsolationForestDetector, HybridDetector, detect_anomaly,
    get_detector, HARD_LIMITS,
)


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
def training_data():
    np.random.seed(42)
    n = 200
    temperature = np.random.normal(325, 20, n)
    pressure = np.random.normal(20, 3, n)
    flow_rate = np.random.normal(50, 8, n)
    X = np.column_stack([temperature, pressure, flow_rate])
    feature_names = ['temperature', 'pressure', 'flow_rate']
    return X, feature_names


# ---------------------------------------------------------------------------
# Detection contract
# ---------------------------------------------------------------------------

class TestDetection:
    def test_to_dict(self):
        d = Detection(
            is_anomaly=True, anomaly_score=0.85, detector='isolation_forest',
            explanation='Temperature spike',
            contributing_sensors={'temperature': 3.2, 'pressure': 1.5},
            confidence=0.9,
        )
        result = d.to_dict()
        assert result['is_anomaly'] is True
        assert result['anomaly_score'] == 0.85
        assert result['detector'] == 'isolation_forest'
        assert result['contributing_sensors']['temperature'] == 3.2
        assert result['confidence'] == 0.9

    def test_default_contributing_sensors(self):
        d = Detection(is_anomaly=False, anomaly_score=0.1, detector='rule', explanation='ok')
        assert d.contributing_sensors == {}


# ---------------------------------------------------------------------------
# IsolationForestDetector
# ---------------------------------------------------------------------------

class TestIsolationForestDetector:
    def test_train_and_predict(self, training_data):
        X, features = training_data
        detector = IsolationForestDetector()
        detector.train('Chemical Reactor', X, features)
        assert detector._trained['Chemical Reactor']

    def test_predict_normal(self, training_data):
        X, features = training_data
        detector = IsolationForestDetector()
        detector.train('Chemical Reactor', X, features)
        score, is_anomaly = detector.predict('Chemical Reactor', np.array([325.0, 20.0, 50.0]))
        assert score < 0.7

    def test_predict_anomalous(self, training_data):
        X, features = training_data
        detector = IsolationForestDetector()
        detector.train('Chemical Reactor', X, features)
        score, is_anomaly = detector.predict('Chemical Reactor', np.array([800.0, 50.0, 100.0]))
        assert score > 0.3

    def test_untrained_returns_zero(self):
        detector = IsolationForestDetector()
        score, is_anomaly = detector.predict('Chemical Reactor', np.array([325.0, 20.0, 50.0]))
        assert score == 0.0
        assert is_anomaly is False

    def test_insufficient_data(self):
        detector = IsolationForestDetector()
        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        detector.train('Chemical Reactor', X, ['a', 'b', 'c'])
        assert not detector._trained.get('Chemical Reactor')

    def test_save_and_load(self, training_data, tmp_path):
        X, features = training_data
        detector = IsolationForestDetector()
        detector.MODEL_DIR = str(tmp_path)
        detector.train('Chemical Reactor', X, features)
        path = detector.save('Chemical Reactor')
        assert os.path.exists(path)

        detector2 = IsolationForestDetector()
        detector2.MODEL_DIR = str(tmp_path)
        loaded = detector2.load('Chemical Reactor')
        assert loaded
        assert detector2._trained['Chemical Reactor']

        s1, a1 = detector.predict('Chemical Reactor', np.array([800.0, 50.0, 100.0]))
        s2, a2 = detector2.predict('Chemical Reactor', np.array([800.0, 50.0, 100.0]))
        assert abs(s1 - s2) < 0.001

    def test_load_nonexistent(self, tmp_path):
        detector = IsolationForestDetector()
        detector.MODEL_DIR = str(tmp_path)
        assert detector.load('Nonexistent') is False

    def test_is_available(self, training_data):
        X, features = training_data
        detector = IsolationForestDetector()
        assert not detector.is_available
        detector.train('Chemical Reactor', X, features)
        assert detector.is_available


# ---------------------------------------------------------------------------
# HybridDetector
# ---------------------------------------------------------------------------

class TestHybridDetector:
    def _make_detector(self, training_data):
        X, features = training_data
        d = HybridDetector()
        d.train('Chemical Reactor', X, features)
        return d

    def test_normal_readings(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert not detection.is_anomaly
        assert detection.anomaly_score < 1.0
        assert detection.detector in ('isolation_forest', 'rule_hybrid')

    def test_hard_limit_breach_wins(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Chemical Reactor', {
            'temperature': 500.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert detection.is_anomaly
        assert detection.anomaly_score == 1.0
        assert detection.detector == 'rule_hybrid'
        assert 'Hard-limit' in detection.explanation
        assert detection.confidence == 1.0

    def test_hard_limit_below_min(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 2.0, 'flow_rate': 50.0,
        })
        assert detection.is_anomaly
        assert detection.anomaly_score == 1.0
        assert 'below minimum' in detection.explanation

    def test_ml_anomaly(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Chemical Reactor', {
            'temperature': 750.0, 'pressure': 48.0, 'flow_rate': 95.0,
        })
        assert detection.anomaly_score > 0.3

    def test_contributing_sensors_ranked(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Chemical Reactor', {
            'temperature': 500.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert 'temperature' in detection.contributing_sensors

    def test_timestamp_defaults(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert detection.timestamp is not None

    def test_untrained_ml_fallback(self):
        d = HybridDetector()
        detection = d.detect('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert not detection.is_anomaly
        assert detection.detector == 'rule_hybrid'

    def test_unknown_machine_type(self, training_data):
        d = self._make_detector(training_data)
        detection = d.detect('Unknown Machine', {
            'temperature': 325.0, 'pressure': 20.0,
        })
        assert not detection.is_anomaly


# ---------------------------------------------------------------------------
# detect_anomaly convenience
# ---------------------------------------------------------------------------

class TestDetectAnomaly:
    def test_convenience_function(self):
        detection = detect_anomaly('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert isinstance(detection, Detection)
        assert hasattr(detection, 'is_anomaly')


# ---------------------------------------------------------------------------
# F7 API endpoints
# ---------------------------------------------------------------------------

class TestMLAPI:
    def test_ml_status(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/ml/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']

    def test_train_ml_no_machine(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/ml/train', json={})
        assert resp.status_code == 400

    def test_train_ml_no_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/ml/train', json={'machine_id': 1})
        assert resp.status_code == 400

    def test_detect_on_machine_no_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/ml/detect/1')
        assert resp.status_code == 404  # no readings

    def test_train_and_detect_e2e(self, client, app_obj):
        """End-to-end: insert readings, train, then detect."""
        with app.app_context():
            _seed_machine()
            _login_admin(client)
            from datetime import datetime, timedelta
            import random
            random.seed(42)
            base = datetime.utcnow() - timedelta(minutes=100)
            for i in range(100):
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='temperature',
                    value=325.0 + random.gauss(0, 10), unit='°C',
                    timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='pressure',
                    value=20.0 + random.gauss(0, 1), unit='bar',
                    timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='flow_rate',
                    value=50.0 + random.gauss(0, 2), unit='L/min',
                    timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
            db.session.commit()

        resp = client.post('/api/admin/ml/train', json={
            'machine_id': 1, 'hours': 48,
        })
        data = resp.get_json()
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
        assert data['success']

        resp2 = client.get('/api/admin/ml/detect/1')
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2['success']
        assert 'detection' in data2
