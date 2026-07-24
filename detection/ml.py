"""F7: ML anomaly detection (unsupervised).

Provides Isolation Forest detector with rule-fusion. The detector learns
"normal" operating patterns and scores live windows, while hard-limit
breaches always override ML output (rules always win for safety limits).

Detection contract:
    is_anomaly: bool
    anomaly_score: float (0.0-1.0)
    detector: str (e.g. "isolation_forest", "rule_hybrid")
    explanation: str (human-readable reason)
    contributing_sensors: dict
    confidence: float (0.0-1.0)
"""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection contract
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """Unified output from any detector (F7 contract)."""
    is_anomaly: bool
    anomaly_score: float          # 0.0 = normal, 1.0 = certain anomaly
    detector: str                 # which detector produced this
    explanation: str              # human-readable
    contributing_sensors: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0       # how sure the detector is (0-1)
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'is_anomaly': self.is_anomaly,
            'anomaly_score': round(self.anomaly_score, 4),
            'detector': self.detector,
            'explanation': self.explanation,
            'contributing_sensors': self.contributing_sensors,
            'confidence': round(self.confidence, 4),
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


# ---------------------------------------------------------------------------
# Hard limits — rules that ML must NEVER override
# ---------------------------------------------------------------------------

HARD_LIMITS = {
    'Chemical Reactor': {
        'temperature': {'min': 250, 'max': 450, 'unit': '°C'},
        'pressure': {'min': 5, 'max': 35, 'unit': 'bar'},
        'flow_rate': {'min': 5, 'max': 95, 'unit': 'L/min'},
    },
    'Biotech Fermenter': {
        'temperature': {'min': 25, 'max': 55, 'unit': '°C'},
        'ph': {'min': 5.5, 'max': 8.5, 'unit': 'pH'},
    },
    'Distillation Column': {
        'temperature_top': {'min': 60, 'max': 180, 'unit': '°C'},
        'temperature_bottom': {'min': 120, 'max': 290, 'unit': '°C'},
        'pressure': {'min': 0.2, 'max': 4.5, 'unit': 'bar'},
    },
}


# ---------------------------------------------------------------------------
# Isolation Forest detector
# ---------------------------------------------------------------------------

class IsolationForestDetector:
    """Unsupervised anomaly detector using scikit-learn's IsolationForest.

    Trains on healthy historical data, scores live windows. Each machine
    type gets its own model.
    """

    MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models', 'ml')

    def __init__(self, model_type: str = 'isolation_forest', contamination: float = 0.05):
        self.model_type = model_type
        self.contamination = contamination
        self._models: Dict[str, IsolationForest] = {}
        self._scalers: Dict[str, StandardScaler] = {}
        self._trained: Dict[str, bool] = {}

    def train(self, machine_type: str, X: np.ndarray, feature_names: List[str]) -> None:
        """Train an Isolation Forest on healthy data.

        Args:
            machine_type: key into HARD_LIMITS
            X: 2D array, shape (n_samples, n_features)
            feature_names: list of sensor names matching columns
        """
        if X.ndim != 2 or X.shape[0] < 10:
            logger.warning("Insufficient training data for %s: %s", machine_type, X.shape)
            return

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = IsolationForest(
            contamination=self.contamination,
            n_estimators=100,
            max_samples='auto',
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_scaled)

        self._models[machine_type] = clf
        self._scalers[machine_type] = scaler
        self._trained[machine_type] = True
        logger.info("Trained Isolation Forest for %s on %d samples, %d features",
                     machine_type, X.shape[0], X.shape[1])

    def predict(self, machine_type: str, x: np.ndarray) -> Tuple[float, bool]:
        """Score a single sample.

        Returns:
            (anomaly_score, is_anomaly) where score ∈ [0, 1].
        """
        if not self._trained.get(machine_type):
            return 0.0, False

        scaler = self._scalers[machine_type]
        clf = self._models[machine_type]
        x_scaled = scaler.transform(x.reshape(1, -1))

        raw_score = clf.decision_function(x_scaled)[0]
        # decision_function returns score where negative = anomaly.
        # Map to [0, 1] range: raw_score of -0.5 → 1.0, 0.5 → 0.0
        anomaly_score = float(np.clip(0.5 - raw_score, 0.0, 1.0))
        is_anomaly = clf.predict(x_scaled)[0] == -1
        return anomaly_score, is_anomaly

    def save(self, machine_type: str) -> str:
        """Persist model + scaler to disk. Returns file path."""
        os.makedirs(self.MODEL_DIR, exist_ok=True)
        path = os.path.join(self.MODEL_DIR, f"{machine_type.replace(' ', '_')}.pkl")
        payload = {
            'model': self._models.get(machine_type),
            'scaler': self._scalers.get(machine_type),
            'model_type': self.model_type,
            'trained_at': datetime.utcnow().isoformat(),
        }
        with open(path, 'wb') as f:
            pickle.dump(payload, f)
        logger.info("Saved model for %s to %s", machine_type, path)
        return path

    def load(self, machine_type: str) -> bool:
        """Load model from disk. Returns True if successful."""
        path = os.path.join(self.MODEL_DIR, f"{machine_type.replace(' ', '_')}.pkl")
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'rb') as f:
                payload = pickle.load(f)
            self._models[machine_type] = payload['model']
            self._scalers[machine_type] = payload['scaler']
            self._trained[machine_type] = True
            logger.info("Loaded model for %s (trained %s)", machine_type, payload.get('trained_at'))
            return True
        except Exception as e:
            logger.error("Failed to load model for %s: %s", machine_type, e)
            return False

    @property
    def is_available(self) -> bool:
        return any(self._trained.values())


# ---------------------------------------------------------------------------
# Hybrid detector — fuses ML + rules
# ---------------------------------------------------------------------------

class HybridDetector:
    """Combines Isolation Forest with hard-limit rules.

    Rules always win: if a hard-limit breach is detected, the anomaly score
    is set to 1.0 and the explanation cites the rule. ML provides nuance
    for softer anomalies (drift, correlation changes).
    """

    def __init__(self):
        self.ml = IsolationForestDetector()
        self._feature_names: Dict[str, List[str]] = {}

    def train(self, machine_type: str, X: np.ndarray, feature_names: List[str]) -> None:
        self._feature_names[machine_type] = feature_names
        self.ml.train(machine_type, X, feature_names)

    def detect(self, machine_type: str, readings: Dict[str, float],
               timestamp: Optional[datetime] = None) -> Detection:
        """Run hybrid detection on a set of current readings.

        Args:
            machine_type: one of HARD_LIMITS keys
            readings: {sensor_type: value}
            timestamp: optional, defaults to now

        Returns:
            Detection with fused ML + rule output
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # --- Step 1: Check hard limits (rules always win) ---
        hard_limit_breaches: Dict[str, str] = {}
        limits = HARD_LIMITS.get(machine_type, {})
        for sensor_type, value in readings.items():
            if sensor_type in limits:
                lim = limits[sensor_type]
                if value < lim['min']:
                    hard_limit_breaches[sensor_type] = (
                        f"{sensor_type}={value:.1f}{lim['unit']} below minimum {lim['min']}{lim['unit']}"
                    )
                elif value > lim['max']:
                    hard_limit_breaches[sensor_type] = (
                        f"{sensor_type}={value:.1f}{lim['unit']} above maximum {lim['max']}{lim['unit']}"
                    )

        # --- Step 2: ML scoring ---
        ml_score = 0.0
        ml_anomaly = False
        feature_names = self._feature_names.get(machine_type, [])
        if self.ml._trained.get(machine_type) and feature_names:
            x = np.array([readings.get(f, 0.0) for f in feature_names])
            ml_score, ml_anomaly = self.ml.predict(machine_type, x)

        # --- Step 3: Fuse ---
        if hard_limit_breaches:
            # Rules win
            score = 1.0
            is_anomaly = True
            detector = "rule_hybrid"
            explanation = "Hard-limit breach: " + "; ".join(hard_limit_breaches.values())
            confidence = 1.0
            contributing = {s: 1.0 for s in hard_limit_breaches}
        elif ml_anomaly and ml_score > 0.6:
            # ML-only anomaly
            score = ml_score
            is_anomaly = True
            detector = "isolation_forest"
            # Find top contributing sensors via feature importance or deviation
            contributing = self._rank_contributing(machine_type, readings, feature_names)
            explanation = "ML detected anomalous pattern: " + ", ".join(
                f"{k} (score {v:.2f})" for k, v in sorted(contributing.items(), key=lambda x: -x[1])[:3]
            )
            confidence = ml_score
        elif ml_score > 0.3:
            # Warning zone — not fully anomalous
            score = ml_score
            is_anomaly = False
            detector = "isolation_forest"
            contributing = self._rank_contributing(machine_type, readings, feature_names)
            explanation = "Elevated ML score: " + ", ".join(
                f"{k} ({v:.2f})" for k, v in sorted(contributing.items(), key=lambda x: -x[1])[:2]
            )
            confidence = ml_score
        else:
            # Normal
            score = ml_score
            is_anomaly = False
            detector = "isolation_forest" if self.ml._trained.get(machine_type) else "rule_hybrid"
            explanation = "All readings within normal bounds"
            confidence = 1.0 - ml_score
            contributing = {}

        return Detection(
            is_anomaly=is_anomaly,
            anomaly_score=score,
            detector=detector,
            explanation=explanation,
            contributing_sensors=contributing,
            confidence=confidence,
            timestamp=timestamp,
        )

    def _rank_contributing(self, machine_type: str, readings: Dict[str, float],
                           feature_names: List[str]) -> Dict[str, float]:
        """Rank how much each sensor deviates from training mean."""
        if not self.ml._trained.get(machine_type):
            return {}
        scaler = self.ml._scalers.get(machine_type)
        if scaler is None:
            return {}
        means = scaler.mean_
        stds = scaler.scale_
        deviations: Dict[str, float] = {}
        for i, name in enumerate(feature_names):
            if name in readings and stds[i] > 0:
                deviations[name] = abs(readings[name] - means[i]) / stds[i]
        return deviations


# ---------------------------------------------------------------------------
# Global instance (lazy init)
# ---------------------------------------------------------------------------

_detector: Optional[HybridDetector] = None


def get_detector() -> HybridDetector:
    global _detector
    if _detector is None:
        _detector = HybridDetector()
        # Try to load saved models
        for mt in HARD_LIMITS:
            _detector.ml.load(mt)
    return _detector


def detect_anomaly(machine_type: str, readings: Dict[str, float],
                   timestamp: Optional[datetime] = None) -> Detection:
    """Convenience function for detection. Used by ingestion pipeline."""
    detector = get_detector()
    return detector.detect(machine_type, readings, timestamp)
