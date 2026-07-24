"""F10: Evaluation harness & model drift monitoring.

Measures detection quality (precision/recall/F1, false-alarm rate, lead time)
against labeled scenarios. Monitors input distribution drift using KS test and PSI.

Every performance claim must come from this harness.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation result storage
# ---------------------------------------------------------------------------

EVAL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'eval_results')


@dataclass
class EvalRun:
    """Result of a single evaluation run."""
    run_id: str
    machine_type: str
    scenario_name: str
    timestamp: str
    total_samples: int
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    false_alarm_rate: float = 0.0
    mean_lead_time_seconds: float = 0.0
    detection_details: List[Dict] = field(default_factory=list)

    def compute_metrics(self) -> None:
        """Compute derived metrics from TP/FP/TN/FN."""
        tp = self.true_positives
        fp = self.false_positives
        tn = self.true_negatives
        fn = self.false_negatives

        self.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        self.recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if self.precision + self.recall > 0:
            self.f1 = 2 * self.precision * self.recall / (self.precision + self.recall)
        else:
            self.f1 = 0.0
        self.false_alarm_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            'run_id': self.run_id,
            'machine_type': self.machine_type,
            'scenario_name': self.scenario_name,
            'timestamp': self.timestamp,
            'total_samples': self.total_samples,
            'true_positives': self.true_positives,
            'false_positives': self.false_positives,
            'true_negatives': self.true_negatives,
            'false_negatives': self.false_negatives,
            'precision': round(self.precision, 4),
            'recall': round(self.recall, 4),
            'f1': round(self.f1, 4),
            'false_alarm_rate': round(self.false_alarm_rate, 4),
            'mean_lead_time_seconds': round(self.mean_lead_time_seconds, 2),
            'detection_details': self.detection_details[-20:],  # last 20
        }


@dataclass
class DriftResult:
    """Result of a drift check between training and current distributions."""
    sensor_type: str
    ks_statistic: float
    ks_p_value: float
    psi: float              # Population Stability Index
    drifted: bool           # True if significant drift detected
    details: str = ''

    def to_dict(self) -> dict:
        return {
            'sensor_type': self.sensor_type,
            'ks_statistic': round(self.ks_statistic, 4),
            'ks_p_value': round(self.ks_p_value, 6),
            'psi': round(self.psi, 4),
            'drifted': self.drifted,
            'details': self.details,
        }


# ---------------------------------------------------------------------------
# Evaluation harness
# ---------------------------------------------------------------------------

class EvalHarness:
    """Runs detection on labeled data and computes quality metrics.

    Usage:
        harness = EvalHarness()
        results = harness.evaluate(
            machine_type='Chemical Reactor',
            readings_with_labels=[(readings_dict, is_truly_anomaly), ...],
            detector_func=detect_explainable,
        )
    """

    def __init__(self):
        os.makedirs(EVAL_DIR, exist_ok=True)

    def evaluate(self, machine_type: str, scenario_name: str,
                 labeled_data: List[Tuple[Dict[str, float], bool]],
                 detector_func,
                 timestamps: Optional[List[datetime]] = None) -> EvalRun:
        """Evaluate a detector against labeled data.

        Args:
            machine_type: for context
            scenario_name: label for this evaluation
            labeled_data: list of (readings_dict, is_anomaly_label)
            detector_func: callable(machine_type, readings) -> Detection
            timestamps: optional timestamps for lead-time calculation

        Returns:
            EvalRun with all computed metrics
        """
        run_id = f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{scenario_name}"
        run = EvalRun(
            run_id=run_id,
            machine_type=machine_type,
            scenario_name=scenario_name,
            timestamp=datetime.utcnow().isoformat(),
            total_samples=len(labeled_data),
        )

        first_anomaly_idx = None
        for i, (readings, is_anomaly) in enumerate(labeled_data):
            try:
                detection = detector_func(machine_type, readings)
                detected = detection.is_anomaly
            except Exception as e:
                logger.warning("Detection failed at sample %d: %s", i, e)
                detected = False
                detection = None

            # Classification
            if is_anomaly and detected:
                run.true_positives += 1
                if first_anomaly_idx is None:
                    first_anomaly_idx = i
            elif not is_anomaly and detected:
                run.false_positives += 1
            elif not is_anomaly and not detected:
                run.true_negatives += 1
            elif is_anomaly and not detected:
                run.false_negatives += 1

            run.detection_details.append({
                'index': i,
                'true_label': is_anomaly,
                'detected': detected,
                'score': detection.anomaly_score if detection else 0.0,
                'detector': detection.detector if detection else 'error',
            })

        run.compute_metrics()

        # Lead time: average time between first anomaly detection and first true anomaly
        if first_anomaly_idx is not None and timestamps:
            detection_times = []
            for i, (readings, is_anomaly) in enumerate(labeled_data):
                if i >= first_anomaly_idx and run.detection_details[i]['detected']:
                    detection_times.append(i)
            if detection_times:
                lead_times = [t - first_anomaly_idx for t in detection_times]
                run.mean_lead_time_seconds = float(np.mean(lead_times))

        return run

    def save_run(self, run: EvalRun) -> str:
        """Persist an eval run to disk. Returns file path."""
        path = os.path.join(EVAL_DIR, f"{run.run_id}.json")
        with open(path, 'w') as f:
            json.dump(run.to_dict(), f, indent=2)
        logger.info("Saved eval run to %s", path)
        return path

    def load_runs(self, scenario_name: Optional[str] = None,
                  limit: int = 50) -> List[EvalRun]:
        """Load recent eval runs, optionally filtered by scenario."""
        runs = []
        for fname in sorted(os.listdir(EVAL_DIR), reverse=True):
            if not fname.endswith('.json'):
                continue
            if scenario_name and scenario_name not in fname:
                continue
            path = os.path.join(EVAL_DIR, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
                run = EvalRun(
                    run_id=data['run_id'],
                    machine_type=data['machine_type'],
                    scenario_name=data['scenario_name'],
                    timestamp=data['timestamp'],
                    total_samples=data['total_samples'],
                    true_positives=data.get('true_positives', 0),
                    false_positives=data.get('false_positives', 0),
                    true_negatives=data.get('true_negatives', 0),
                    false_negatives=data.get('false_negatives', 0),
                    mean_lead_time_seconds=data.get('mean_lead_time_seconds', 0),
                )
                run.precision = data.get('precision', 0)
                run.recall = data.get('recall', 0)
                run.f1 = data.get('f1', 0)
                run.false_alarm_rate = data.get('false_alarm_rate', 0)
                runs.append(run)
            except Exception as e:
                logger.warning("Failed to load eval run %s: %s", path, e)
            if len(runs) >= limit:
                break
        return runs


# ---------------------------------------------------------------------------
# Drift monitoring
# ---------------------------------------------------------------------------

class DriftMonitor:
    """Monitors input distribution drift using KS test and Population Stability Index.

    Compares current readings against a training baseline distribution.
    """

    def __init__(self):
        self._baselines: Dict[str, Dict[str, np.ndarray]] = {}

    def set_baseline(self, machine_type: str, sensor_type: str,
                     training_values: np.ndarray) -> None:
        """Set the baseline distribution from training data.

        Args:
            machine_type: machine type key
            sensor_type: sensor name
            training_values: 1D array of training values
        """
        key = f"{machine_type}:{sensor_type}"
        self._baselines[key] = training_values.copy()

    def set_baseline_from_dict(self, machine_type: str,
                                sensor_readings: Dict[str, List[float]]) -> None:
        """Set baselines for all sensors from a dict of value lists."""
        for sensor, values in sensor_readings.items():
            self.set_baseline(machine_type, sensor, np.array(values))

    def check_drift(self, machine_type: str, sensor_type: str,
                    current_values: np.ndarray,
                    ks_alpha: float = 0.05,
                    psi_threshold: float = 0.2) -> DriftResult:
        """Check if current distribution has drifted from baseline.

        Args:
            machine_type: machine type key
            sensor_type: sensor name
            current_values: 1D array of recent values
            ks_alpha: significance level for KS test (default 0.05)
            psi_threshold: PSI threshold for drift detection (default 0.2)

        Returns:
            DriftResult with KS statistic, PSI, and drift flag
        """
        key = f"{machine_type}:{sensor_type}"
        baseline = self._baselines.get(key)

        if baseline is None or len(baseline) < 5:
            return DriftResult(
                sensor_type=sensor_type,
                ks_statistic=0.0,
                ks_p_value=1.0,
                psi=0.0,
                drifted=False,
                details='No baseline available',
            )

        if len(current_values) < 5:
            return DriftResult(
                sensor_type=sensor_type,
                ks_statistic=0.0,
                ks_p_value=1.0,
                psi=0.0,
                drifted=False,
                details='Insufficient current data',
            )

        # KS test
        ks_stat, ks_p = ks_2samp(baseline, current_values)

        # Population Stability Index
        psi = self._compute_psi(baseline, current_values)

        drifted = (ks_p < ks_alpha) or (psi > psi_threshold)

        if drifted:
            details = (f"Drift detected: KS p={ks_p:.4f} (< {ks_alpha}), "
                       f"PSI={psi:.4f} (> {psi_threshold})")
        else:
            details = f"No drift: KS p={ks_p:.4f}, PSI={psi:.4f}"

        return DriftResult(
            sensor_type=sensor_type,
            ks_statistic=ks_stat,
            ks_p_value=ks_p,
            psi=psi,
            drifted=drifted,
            details=details,
        )

    def check_all_sensors(self, machine_type: str,
                          current_readings: Dict[str, List[float]],
                          ks_alpha: float = 0.05,
                          psi_threshold: float = 0.2) -> List[DriftResult]:
        """Check drift for all sensors that have baselines."""
        results = []
        for sensor, values in current_readings.items():
            result = self.check_drift(
                machine_type, sensor, np.array(values), ks_alpha, psi_threshold
            )
            results.append(result)
        return results

    @staticmethod
    def _compute_psi(expected: np.ndarray, actual: np.ndarray,
                     bins: int = 10) -> float:
        """Compute Population Stability Index.

        PSI < 0.1: no significant change
        0.1 <= PSI < 0.2: moderate change
        PSI >= 0.2: significant drift
        """
        # Create bins from combined data
        all_values = np.concatenate([expected, actual])
        bin_edges = np.linspace(np.min(all_values), np.max(all_values), bins + 1)

        # Compute proportions
        expected_hist, _ = np.histogram(expected, bins=bin_edges)
        actual_hist, _ = np.histogram(actual, bins=bin_edges)

        # Avoid division by zero
        expected_pct = (expected_hist + 1) / (len(expected) + bins)
        actual_pct = (actual_hist + 1) / (len(actual) + bins)

        psi = float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))
        return psi

    def save_baselines(self, machine_type: str) -> str:
        """Save baselines to disk."""
        os.makedirs(EVAL_DIR, exist_ok=True)
        path = os.path.join(EVAL_DIR, f"baselines_{machine_type.replace(' ', '_')}.json")
        data = {}
        for key, values in self._baselines.items():
            if key.startswith(machine_type):
                data[key] = values.tolist()
        with open(path, 'w') as f:
            json.dump(data, f)
        return path

    def load_baselines(self, machine_type: str) -> bool:
        """Load baselines from disk."""
        path = os.path.join(EVAL_DIR, f"baselines_{machine_type.replace(' ', '_')}.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            for key, values in data.items():
                self._baselines[key] = np.array(values)
            return True
        except Exception as e:
            logger.error("Failed to load baselines: %s", e)
            return False


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

_eval_harness: Optional[EvalHarness] = None
_drift_monitor: Optional[DriftMonitor] = None


def get_eval_harness() -> EvalHarness:
    global _eval_harness
    if _eval_harness is None:
        _eval_harness = EvalHarness()
    return _eval_harness


def get_drift_monitor() -> DriftMonitor:
    global _drift_monitor
    if _drift_monitor is None:
        _drift_monitor = DriftMonitor()
    return _drift_monitor
