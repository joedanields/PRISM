"""Tests for F11: Explainable, physics-informed hybrid detection.

Covers PhysicsDetector (rate-of-change, stuck sensor, cross-sensor rules),
ExplainableDetector layer integration, and the detect endpoint.
"""

import os
import sys

import numpy as np
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app, db, Machine, SensorReading, User
from detection.explain import (
    PhysicsDetector, ExplainableDetector, RuleResult,
    detect_explainable, get_explainable_detector,
    RATE_OF_CHANGE_LIMITS, CROSS_SENSOR_RULES, STUCK_VARIANCE_THRESHOLD,
)
from detection.ml import Detection


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


# ---------------------------------------------------------------------------
# PhysicsDetector
# ---------------------------------------------------------------------------

class TestPhysicsDetector:
    def test_rate_of_change_normal(self):
        pd = PhysicsDetector()
        prev = {'temperature': 325.0, 'pressure': 20.0}
        curr = {'temperature': 326.0, 'pressure': 20.1}
        results = pd.check_rate_of_change('Chemical Reactor', curr, prev, 10.0)
        assert len(results) == 2
        assert all(not r.triggered for r in results)

    def test_rate_of_change_exceeded(self):
        pd = PhysicsDetector()
        prev = {'temperature': 325.0, 'pressure': 20.0}
        curr = {'temperature': 400.0, 'pressure': 20.1}  # 75°C in 1s = 75°C/s > 5°C/s
        results = pd.check_rate_of_change('Chemical Reactor', curr, prev, 1.0)
        temp_result = [r for r in results if 'temperature' in r.rule_name][0]
        assert temp_result.triggered
        assert temp_result.severity == 'critical'  # > 2x limit

    def test_rate_of_change_warning(self):
        pd = PhysicsDetector()
        prev = {'temperature': 325.0}
        curr = {'temperature': 335.0}  # 10°C in 1s = 10°C/s > 5°C/s but < 10°C/s (2x)
        results = pd.check_rate_of_change('Chemical Reactor', curr, prev, 1.0)
        temp_result = [r for r in results if 'temperature' in r.rule_name][0]
        assert temp_result.triggered
        assert temp_result.severity == 'warning'

    def test_rate_of_change_zero_elapsed(self):
        pd = PhysicsDetector()
        results = pd.check_rate_of_change('Chemical Reactor', {'temperature': 325}, {'temperature': 320}, 0)
        assert len(results) == 0

    def test_rate_of_change_missing_sensor(self):
        pd = PhysicsDetector()
        results = pd.check_rate_of_change('Chemical Reactor', {}, {'temperature': 325}, 1.0)
        assert len(results) == 0

    def test_stuck_sensor_normal(self):
        pd = PhysicsDetector()
        # Varying values — not stuck
        recent = {'temperature': [325.0 + i * 0.1 for i in range(15)]}
        results = pd.check_stuck_sensor('Chemical Reactor', recent)
        temp_result = [r for r in results if 'temperature' in r.rule_name][0]
        assert not temp_result.triggered

    def test_stuck_sensor_detected(self):
        pd = PhysicsDetector()
        # Identical values — stuck
        recent = {'temperature': [325.0] * 15}
        results = pd.check_stuck_sensor('Chemical Reactor', recent)
        temp_result = [r for r in results if 'temperature' in r.rule_name][0]
        assert temp_result.triggered
        assert 'stuck' in temp_result.description

    def test_stuck_sensor_insufficient_data(self):
        pd = PhysicsDetector()
        recent = {'temperature': [325.0, 325.0, 325.0]}  # only 3 values
        results = pd.check_stuck_sensor('Chemical Reactor', recent)
        temp_result = [r for r in results if 'temperature' in r.rule_name][0]
        assert not temp_result.triggered
        assert 'insufficient' in temp_result.description.lower()

    def test_cross_sensor_distillation_ok(self):
        pd = PhysicsDetector()
        readings = {'temperature_top': 100.0, 'temperature_bottom': 200.0}
        results = pd.check_cross_sensor('Distillation Column', readings)
        assert len(results) == 1
        assert not results[0].triggered  # bottom > top, OK

    def test_cross_sensor_distillation_violation(self):
        pd = PhysicsDetector()
        readings = {'temperature_top': 200.0, 'temperature_bottom': 100.0}  # top > bottom!
        results = pd.check_cross_sensor('Distillation Column', readings)
        assert results[0].triggered
        assert 'Bottom temperature' in results[0].description

    def test_cross_sensor_reactor_blockage(self):
        pd = PhysicsDetector()
        readings = {'flow_rate': 10.0, 'pressure': 35.0}  # low flow + high pressure
        results = pd.check_cross_sensor('Chemical Reactor', readings)
        assert results[0].triggered
        assert 'blockage' in results[0].description.lower()

    def test_cross_sensor_no_rules(self):
        pd = PhysicsDetector()
        results = pd.check_cross_sensor('Unknown Machine', {'temperature': 100})
        assert len(results) == 0

    def test_rule_result_to_dict_behavior(self):
        r = RuleResult(rule_name='test', description='test desc', triggered=True,
                       severity='warning', details='extra')
        assert r.triggered
        assert r.severity == 'warning'


# ---------------------------------------------------------------------------
# ExplainableDetector
# ---------------------------------------------------------------------------

class TestExplainableDetector:
    def test_normal_readings(self):
        ed = ExplainableDetector()
        detection = ed.detect('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert not detection.is_anomaly
        assert detection.anomaly_score < 0.7
        assert 'hard_limit' not in detection.detector

    def test_hard_limit_always_wins(self):
        ed = ExplainableDetector()
        detection = ed.detect('Chemical Reactor', {
            'temperature': 500.0,  # above max 450
            'pressure': 20.0,
            'flow_rate': 50.0,
        })
        assert detection.is_anomaly
        assert detection.anomaly_score == 1.0
        assert 'hard_limit' in detection.detector
        assert 'SAFETY' in detection.explanation

    def test_physics_rate_of_change(self):
        ed = ExplainableDetector()
        ts1 = datetime(2026, 1, 1, 12, 0, 0)
        ts2 = ts1 + timedelta(seconds=1)
        # Set up history
        ed.update_history('Chemical Reactor', {'temperature': 325.0}, ts1)
        # Now rapid change
        detection = ed.detect('Chemical Reactor', {'temperature': 400.0}, ts2)
        assert 'physics' in detection.detector
        assert 'PHYSICS' in detection.explanation

    def test_stuck_sensor_detection(self):
        ed = ExplainableDetector()
        # Build up stuck history
        for i in range(15):
            ed.update_history('Chemical Reactor', {'temperature': 325.0},
                              datetime(2026, 1, 1, 12, 0, i))
        recent = ed.get_recent_values('Chemical Reactor')
        detection = ed.detect('Chemical Reactor', {'temperature': 325.0},
                              datetime(2026, 1, 1, 12, 0, 15), recent)
        assert 'stuck' in detection.explanation.lower() or detection.anomaly_score >= 0.7

    def test_explanation_cites_layer(self):
        ed = ExplainableDetector()
        detection = ed.detect('Chemical Reactor', {
            'temperature': 500.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert any(word in detection.explanation for word in ['SAFETY', 'PHYSICS', 'ML', 'normal'])

    def test_update_history_maintains_buffer(self):
        ed = ExplainableDetector()
        ts = datetime(2026, 1, 1, 12, 0, 0)
        for i in range(30):
            ed.update_history('Chemical Reactor', {'temperature': 325.0 + i},
                              ts + timedelta(seconds=i))
        recent = ed.get_recent_values('Chemical Reactor')
        assert len(recent['temperature']) <= 20  # buffer limit

    def test_unknown_machine_type(self):
        ed = ExplainableDetector()
        detection = ed.detect('Unknown Machine', {'sensor': 100.0})
        assert not detection.is_anomaly

    def test_multiple_sensors_normal(self):
        ed = ExplainableDetector()
        detection = ed.detect('Chemical Reactor', {
            'temperature': 325.0,
            'pressure': 20.0,
            'flow_rate': 50.0,
        })
        assert not detection.is_anomaly

    def test_detect_explainable_convenience(self):
        detection = detect_explainable('Chemical Reactor', {
            'temperature': 325.0, 'pressure': 20.0, 'flow_rate': 50.0,
        })
        assert isinstance(detection, Detection)

    def test_get_explainable_detector_singleton(self):
        d1 = get_explainable_detector()
        d2 = get_explainable_detector()
        assert d1 is d2


# ---------------------------------------------------------------------------
# Configuration completeness
# ---------------------------------------------------------------------------

class TestConfigCompleteness:
    def test_rate_of_change_for_all_machine_types(self):
        """All machine types in HARD_LIMITS should have rate-of-change limits."""
        from detection.ml import HARD_LIMITS
        for mt in HARD_LIMITS:
            assert mt in RATE_OF_CHANGE_LIMITS, f"Missing rate-of-change limits for {mt}"

    def test_stuck_threshold_for_all_machine_types(self):
        from detection.ml import HARD_LIMITS
        for mt in HARD_LIMITS:
            assert mt in STUCK_VARIANCE_THRESHOLD, f"Missing stuck threshold for {mt}"

    def test_cross_sensor_rules_subset_ok(self):
        """Not all machine types need cross-sensor rules, but defined ones should work."""
        pd = PhysicsDetector()
        for mt, rules in CROSS_SENSOR_RULES.items():
            assert len(rules) > 0
            for rule in rules:
                assert 'name' in rule
                assert 'check' in rule


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

class TestExplainableAPI:
    def test_detect_with_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
            base = datetime.utcnow() - timedelta(minutes=5)
            for i in range(10):
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='temperature',
                    value=325.0 + i * 0.1, unit='°C',
                    timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good'))
            db.session.commit()

        resp = client.get('/api/admin/detect/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']
        assert 'detection' in data
        assert 'explanation' in data['detection']
