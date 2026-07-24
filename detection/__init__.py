"""Detection package — ML anomaly detection, evaluation, and explainable detection."""

from detection.ml import Detection, detect_anomaly, get_detector, HybridDetector, IsolationForestDetector
from detection.eval import EvalHarness, EvalRun, DriftMonitor, DriftResult, get_eval_harness, get_drift_monitor
from detection.explain import ExplainableDetector, PhysicsDetector, detect_explainable, get_explainable_detector

__all__ = [
    'Detection', 'detect_anomaly', 'get_detector', 'HybridDetector', 'IsolationForestDetector',
    'EvalHarness', 'EvalRun', 'DriftMonitor', 'DriftResult', 'get_eval_harness', 'get_drift_monitor',
    'ExplainableDetector', 'PhysicsDetector', 'detect_explainable', 'get_explainable_detector',
]
