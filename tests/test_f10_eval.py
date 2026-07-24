"""Tests for F10: Evaluation harness & drift monitoring.

Covers EvalHarness, EvalRun metrics, DriftMonitor (KS test, PSI), and API endpoints.
"""

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app, db, Machine, SensorReading, User
from detection.eval import (
    EvalHarness, EvalRun, DriftMonitor, DriftResult,
    get_eval_harness, get_drift_monitor, EVAL_DIR,
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
# EvalRun metrics
# ---------------------------------------------------------------------------

class TestEvalRun:
    def test_compute_metrics_perfect(self):
        run = EvalRun(run_id='test', machine_type='X', scenario_name='s',
                       timestamp='2026-01-01', total_samples=100,
                       true_positives=50, false_positives=0,
                       true_negatives=45, false_negatives=5)
        run.compute_metrics()
        assert run.precision == 1.0
        assert run.recall == pytest.approx(50 / 55, abs=0.01)
        assert run.f1 > 0.9

    def test_compute_metrics_all_wrong(self):
        run = EvalRun(run_id='test', machine_type='X', scenario_name='s',
                       timestamp='2026-01-01', total_samples=100,
                       true_positives=0, false_positives=50,
                       true_negatives=0, false_negatives=50)
        run.compute_metrics()
        assert run.precision == 0.0
        assert run.recall == 0.0
        assert run.f1 == 0.0

    def test_compute_metrics_zero_division(self):
        run = EvalRun(run_id='test', machine_type='X', scenario_name='s',
                       timestamp='2026-01-01', total_samples=0)
        run.compute_metrics()
        assert run.precision == 0.0
        assert run.recall == 0.0
        assert run.false_alarm_rate == 0.0

    def test_to_dict(self):
        run = EvalRun(run_id='test', machine_type='X', scenario_name='s',
                       timestamp='2026-01-01', total_samples=10,
                       true_positives=5, false_positives=1,
                       true_negatives=3, false_negatives=1)
        run.compute_metrics()
        d = run.to_dict()
        assert d['run_id'] == 'test'
        assert d['precision'] == pytest.approx(0.833, abs=0.01)
        assert d['total_samples'] == 10


# ---------------------------------------------------------------------------
# EvalHarness
# ---------------------------------------------------------------------------

class TestEvalHarness:
    def test_evaluate_perfect_detection(self):
        harness = EvalHarness()
        # All normal samples correctly identified
        labeled_data = [
            ({'temperature': 325.0, 'pressure': 20.0}, False),
            ({'temperature': 326.0, 'pressure': 20.1}, False),
            ({'temperature': 324.0, 'pressure': 19.9}, False),
        ] * 10

        def always_normal(mt, rd):
            return Detection(is_anomaly=False, anomaly_score=0.1,
                             detector='test', explanation='normal')

        run = harness.evaluate('Chemical Reactor', 'test_normal', labeled_data, always_normal)
        assert run.true_negatives == 30
        assert run.false_positives == 0
        assert run.precision == 0.0  # no TP means precision=0 by our formula
        assert run.false_alarm_rate == 0.0

    def test_evaluate_detects_anomalies(self):
        harness = EvalHarness()
        labeled_data = [
            ({'temperature': 325.0}, False),
            ({'temperature': 326.0}, False),
            ({'temperature': 500.0}, True),   # anomaly
            ({'temperature': 325.0}, False),
            ({'temperature': 600.0}, True),   # anomaly
        ]

        def detect_anomalies(mt, rd):
            is_anom = rd.get('temperature', 0) > 400
            return Detection(is_anomaly=is_anom, anomaly_score=0.9 if is_anom else 0.1,
                             detector='test', explanation='test')

        run = harness.evaluate('Chemical Reactor', 'test_detect', labeled_data, detect_anomalies)
        assert run.true_positives == 2
        assert run.true_negatives == 3
        assert run.false_positives == 0
        assert run.false_negatives == 0
        assert run.precision == 1.0
        assert run.recall == 1.0
        assert run.f1 == 1.0

    def test_evaluate_with_false_alarms(self):
        harness = EvalHarness()
        labeled_data = [
            ({'temperature': 325.0}, False),
            ({'temperature': 326.0}, False),
            ({'temperature': 500.0}, True),
        ]

        def over_sensitive(mt, rd):
            return Detection(is_anomaly=True, anomaly_score=0.9,
                             detector='test', explanation='always anomaly')

        run = harness.evaluate('Chemical Reactor', 'test_fp', labeled_data, over_sensitive)
        assert run.false_positives == 2
        assert run.true_positives == 1
        assert run.false_alarm_rate > 0.9

    def test_evaluate_with_missed_detection(self):
        harness = EvalHarness()
        labeled_data = [
            ({'temperature': 500.0}, True),
            ({'temperature': 600.0}, True),
        ]

        def blind(mt, rd):
            return Detection(is_anomaly=False, anomaly_score=0.1,
                             detector='test', explanation='normal')

        run = harness.evaluate('Chemical Reactor', 'test_fn', labeled_data, blind)
        assert run.false_negatives == 2
        assert run.true_positives == 0
        assert run.recall == 0.0

    def test_save_and_load_run(self, tmp_path):
        import detection.eval as eval_mod
        original_dir = eval_mod.EVAL_DIR
        eval_mod.EVAL_DIR = str(tmp_path)
        try:
            harness = EvalHarness()
            run = EvalRun(run_id='test_save', machine_type='X', scenario_name='s',
                          timestamp='2026-01-01', total_samples=10,
                          true_positives=5, false_positives=1,
                          true_negatives=3, false_negatives=1)
            run.compute_metrics()
            path = harness.save_run(run)
            assert os.path.exists(path)

            loaded = harness.load_runs(scenario_name='s')
            assert len(loaded) >= 1
            assert loaded[0].run_id == 'test_save'
        finally:
            eval_mod.EVAL_DIR = original_dir


# ---------------------------------------------------------------------------
# DriftMonitor
# ---------------------------------------------------------------------------

class TestDriftMonitor:
    def test_no_drift_similar_distributions(self):
        monitor = DriftMonitor()
        np.random.seed(42)
        baseline = np.random.normal(325, 10, 200)
        current = np.random.normal(325, 10, 200)

        monitor.set_baseline('Chemical Reactor', 'temperature', baseline)
        result = monitor.check_drift('Chemical Reactor', 'temperature', current)
        assert not result.drifted
        assert result.psi < 0.2

    def test_drift_different_distributions(self):
        monitor = DriftMonitor()
        np.random.seed(42)
        baseline = np.random.normal(325, 10, 200)
        current = np.random.normal(450, 20, 200)  # shifted mean

        monitor.set_baseline('Chemical Reactor', 'temperature', baseline)
        result = monitor.check_drift('Chemical Reactor', 'temperature', current)
        assert result.drifted
        assert result.ks_p_value < 0.05

    def test_no_baseline(self):
        monitor = DriftMonitor()
        result = monitor.check_drift('Chemical Reactor', 'temperature',
                                      np.array([325.0, 326.0, 324.0, 325.0, 325.5]))
        assert not result.drifted
        assert 'No baseline' in result.details

    def test_insufficient_current_data(self):
        monitor = DriftMonitor()
        monitor.set_baseline('Chemical Reactor', 'temperature', np.random.normal(325, 10, 100))
        result = monitor.check_drift('Chemical Reactor', 'temperature', np.array([325.0]))
        assert not result.drifted
        assert 'Insufficient' in result.details

    def test_check_all_sensors(self):
        monitor = DriftMonitor()
        np.random.seed(42)
        monitor.set_baseline('Chemical Reactor', 'temperature', np.random.normal(325, 10, 100))
        monitor.set_baseline('Chemical Reactor', 'pressure', np.random.normal(20, 2, 100))

        current = {
            'temperature': list(np.random.normal(325, 10, 50)),
            'pressure': list(np.random.normal(20, 2, 50)),
        }
        results = monitor.check_all_sensors('Chemical Reactor', current)
        assert len(results) == 2
        assert all(isinstance(r, DriftResult) for r in results)

    def test_psi_computation(self):
        np.random.seed(42)
        baseline = np.random.normal(0, 1, 1000)
        similar = np.random.normal(0, 1, 1000)
        different = np.random.normal(5, 2, 1000)

        psi_similar = DriftMonitor._compute_psi(baseline, similar)
        psi_different = DriftMonitor._compute_psi(baseline, different)
        assert psi_similar < psi_different
        assert psi_different > 0.2  # significant drift

    def test_drift_result_to_dict(self):
        r = DriftResult(sensor_type='temperature', ks_statistic=0.1,
                        ks_p_value=0.5, psi=0.05, drifted=False, details='ok')
        d = r.to_dict()
        assert d['sensor_type'] == 'temperature'
        assert d['drifted'] is False

    def test_set_baseline_from_dict(self):
        monitor = DriftMonitor()
        monitor.set_baseline_from_dict('Chemical Reactor', {
            'temperature': [325, 326, 324],
            'pressure': [20, 21, 19],
        })
        assert 'Chemical Reactor:temperature' in monitor._baselines
        assert 'Chemical Reactor:pressure' in monitor._baselines


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestEvalAPI:
    def test_eval_results_empty(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/eval/results')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']

    def test_eval_run_no_machine(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/eval/run', json={})
        assert resp.status_code == 400

    def test_eval_run_no_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/eval/run', json={'machine_id': 1})
        assert resp.status_code == 400

    def test_drift_check_no_machine(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/drift/check', json={})
        assert resp.status_code == 400

    def test_drift_check_insufficient_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.post('/api/admin/drift/check', json={'machine_id': 1})
        assert resp.status_code == 400

    def test_explainable_detect_no_data(self, client, app_obj):
        with app.app_context():
            _seed_machine()
            _login_admin(client)
        resp = client.get('/api/admin/detect/1')
        assert resp.status_code == 404

    def test_eval_run_with_data(self, client, app_obj):
        """End-to-end: insert data, run eval."""
        with app.app_context():
            _seed_machine()
            _login_admin(client)
            from datetime import datetime, timedelta
            import random
            random.seed(42)
            base = datetime.utcnow() - timedelta(minutes=100)
            for i in range(50):
                db.session.add(SensorReading(
                    machine_id=1, sensor_type='temperature',
                    value=325.0 + random.gauss(0, 10), unit='°C',
                    timestamp=base + timedelta(minutes=i),
                    source='simulator', quality='good',
                    anomaly_score=random.uniform(0, 0.3)))
            db.session.commit()

        resp = client.post('/api/admin/eval/run', json={
            'machine_id': 1, 'scenario_name': 'test_eval', 'hours': 48,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']
        assert data['run']['total_samples'] > 0
