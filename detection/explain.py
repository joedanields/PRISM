"""F11: Explainable, physics-informed hybrid detection.

Layers:
  1. Hard safety limits (from F7 HARD_LIMITS — always win)
  2. Physics/plausibility checks (rate-of-change, stuck sensor, cross-sensor consistency)
  3. ML score (from F7 IsolationForestDetector)

Every Detection carries a plain-language explanation of which layer fired and why.
Stuck/flatlined sensors are detected even when values are in-range.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from detection.ml import Detection, HARD_LIMITS, get_detector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physics rules configuration
# ---------------------------------------------------------------------------

# Maximum rate of change per sensor per second (units/s)
RATE_OF_CHANGE_LIMITS = {
    'Chemical Reactor': {
        'temperature': 5.0,    # °C/s
        'pressure': 0.5,       # bar/s
        'flow_rate': 10.0,     # L/min/s
    },
    'Biotech Fermenter': {
        'temperature': 1.0,    # °C/s
        'ph': 0.1,             # pH/s
        'dissolved_oxygen': 5.0,
        'agitation': 20.0,     # RPM/s
    },
    'Distillation Column': {
        'temperature_top': 3.0,
        'temperature_bottom': 4.0,
        'pressure': 0.1,
        'reflux_ratio': 1.0,
    },
}

# Cross-sensor physical constraints
CROSS_SENSOR_RULES = {
    'Distillation Column': [
        {
            'name': 'bottom_must_exceed_top',
            'description': 'Bottom temperature must exceed top temperature in distillation',
            'check': lambda readings: readings.get('temperature_bottom', 0) <= readings.get('temperature_top', 0),
            'severity': 'warning',
        },
    ],
    'Chemical Reactor': [
        {
            'name': 'flow_pressure_correlation',
            'description': 'Very low flow with high pressure suggests blockage',
            'check': lambda readings: (
                readings.get('flow_rate', 50) < 15 and readings.get('pressure', 20) > 30
            ),
            'severity': 'warning',
        },
    ],
    'Biotech Fermenter': [
        {
            'name': 'ph_sanity',
            'description': 'pH outside biological viability range',
            'check': lambda readings: (
                readings.get('ph', 7.0) < 5.8 or readings.get('ph', 7.0) > 8.2
            ),
            'severity': 'warning',
        },
    ],
}

# Stuck-sensor detection: if variance over this many recent points is below threshold
STUCK_WINDOW_SIZE = 10
STUCK_VARIANCE_THRESHOLD = {
    'Chemical Reactor': {
        'temperature': 0.01,
        'pressure': 0.005,
        'flow_rate': 0.1,
    },
    'Biotech Fermenter': {
        'temperature': 0.001,
        'ph': 0.0005,
        'dissolved_oxygen': 0.01,
        'agitation': 0.05,
    },
    'Distillation Column': {
        'temperature_top': 0.005,
        'temperature_bottom': 0.01,
        'pressure': 0.001,
        'reflux_ratio': 0.005,
    },
}


# ---------------------------------------------------------------------------
# Result of a single rule check
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    """Result of a single physics/plausibility rule check."""
    rule_name: str
    description: str
    triggered: bool
    severity: str            # 'info', 'warning', 'critical'
    details: str = ''


# ---------------------------------------------------------------------------
# Physics engine
# ---------------------------------------------------------------------------

class PhysicsDetector:
    """Checks physical plausibility constraints that don't need ML."""

    def check_rate_of_change(self, machine_type: str,
                             current: Dict[str, float],
                             previous: Dict[str, float],
                             elapsed_seconds: float) -> List[RuleResult]:
        """Check if any sensor changed faster than physically possible.

        Args:
            machine_type: key into RATE_OF_CHANGE_LIMITS
            current: current sensor readings
            previous: previous sensor readings
            elapsed_seconds: time between readings

        Returns:
            List of RuleResult for each checked sensor.
        """
        limits = RATE_OF_CHANGE_LIMITS.get(machine_type, {})
        results = []
        if elapsed_seconds <= 0:
            return results

        for sensor, max_rate in limits.items():
            if sensor in current and sensor in previous:
                delta = abs(current[sensor] - previous[sensor])
                rate = delta / elapsed_seconds
                if rate > max_rate:
                    results.append(RuleResult(
                        rule_name=f'rate_of_change_{sensor}',
                        description=f'{sensor} changed at {rate:.2f}/s (limit {max_rate}/s)',
                        triggered=True,
                        severity='critical' if rate > max_rate * 2 else 'warning',
                        details=f'Δ={delta:.2f} over {elapsed_seconds:.1f}s',
                    ))
                else:
                    results.append(RuleResult(
                        rule_name=f'rate_of_change_{sensor}',
                        description=f'{sensor} rate OK ({rate:.2f}/s)',
                        triggered=False,
                        severity='info',
                    ))
        return results

    def check_stuck_sensor(self, machine_type: str,
                           recent_values: Dict[str, List[float]]) -> List[RuleResult]:
        """Detect stuck/flatlined sensors by checking variance.

        Args:
            machine_type: key into STUCK_VARIANCE_THRESHOLD
            recent_values: {sensor: [last N values]}

        Returns:
            List of RuleResult for each checked sensor.
        """
        thresholds = STUCK_VARIANCE_THRESHOLD.get(machine_type, {})
        results = []
        for sensor, threshold in thresholds.items():
            values = recent_values.get(sensor, [])
            if len(values) < STUCK_WINDOW_SIZE:
                results.append(RuleResult(
                    rule_name=f'stuck_{sensor}',
                    description=f'{sensor} — insufficient data ({len(values)}/{STUCK_WINDOW_SIZE})',
                    triggered=False,
                    severity='info',
                ))
                continue
            import numpy as np
            variance = float(np.var(values[-STUCK_WINDOW_SIZE:]))
            if variance < threshold:
                results.append(RuleResult(
                    rule_name=f'stuck_{sensor}',
                    description=f'{sensor} appears stuck (variance={variance:.6f} < {threshold})',
                    triggered=True,
                    severity='warning',
                    details=f'Last {STUCK_WINDOW_SIZE} values: {values[-STUCK_WINDOW_SIZE:]}',
                ))
            else:
                results.append(RuleResult(
                    rule_name=f'stuck_{sensor}',
                    description=f'{sensor} variance OK ({variance:.4f})',
                    triggered=False,
                    severity='info',
                ))
        return results

    def check_cross_sensor(self, machine_type: str,
                           readings: Dict[str, float]) -> List[RuleResult]:
        """Check cross-sensor physical consistency rules.

        Args:
            machine_type: key into CROSS_SENSOR_RULES
            readings: current sensor values

        Returns:
            List of RuleResult for each checked rule.
        """
        rules = CROSS_SENSOR_RULES.get(machine_type, [])
        results = []
        for rule in rules:
            try:
                triggered = rule['check'](readings)
            except Exception:
                triggered = False
            results.append(RuleResult(
                rule_name=rule['name'],
                description=rule['description'],
                triggered=triggered,
                severity=rule['severity'] if triggered else 'info',
                details=f'Readings: {readings}' if triggered else '',
            ))
        return results


# ---------------------------------------------------------------------------
# Explainable hybrid detector (F11 layer)
# ---------------------------------------------------------------------------

class ExplainableDetector:
    """Combines hard limits + physics + ML into a single explained verdict.

    Layer order (highest priority wins):
      1. Hard safety limits (score = 1.0, always anomaly)
      2. Physics plausibility rules (score = 0.7-0.9)
      3. ML detection (score from model)
    """

    def __init__(self):
        self.physics = PhysicsDetector()
        self._previous_readings: Dict[str, Dict[str, float]] = {}
        self._previous_timestamps: Dict[str, datetime] = {}
        self._recent_values: Dict[str, Dict[str, List[float]]] = {}

    def detect(self, machine_type: str,
               readings: Dict[str, float],
               timestamp: Optional[datetime] = None,
               recent_values: Optional[Dict[str, List[float]]] = None) -> Detection:
        """Run all detection layers and produce an explained verdict.

        Args:
            machine_type: machine type key
            readings: {sensor_type: value}
            timestamp: optional, defaults to now
            recent_values: {sensor: [last N values]} for stuck detection

        Returns:
            Detection with explanation citing which layer fired
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        explanations: List[str] = []
        all_contributing: Dict[str, float] = {}
        max_score = 0.0
        fired_layer = 'none'

        # --- Layer 1: Hard limits ---
        limits = HARD_LIMITS.get(machine_type, {})
        for sensor, value in readings.items():
            if sensor in limits:
                lim = limits[sensor]
                if value < lim['min']:
                    explanations.append(
                        f"SAFETY: {sensor}={value:.1f}{lim['unit']} below minimum {lim['min']}{lim['unit']}"
                    )
                    all_contributing[sensor] = 1.0
                    max_score = 1.0
                    fired_layer = 'hard_limit'
                elif value > lim['max']:
                    explanations.append(
                        f"SAFETY: {sensor}={value:.1f}{lim['unit']} above maximum {lim['max']}{lim['unit']}"
                    )
                    all_contributing[sensor] = 1.0
                    max_score = 1.0
                    fired_layer = 'hard_limit'

        # --- Layer 2: Physics rules (only if no hard-limit breach) ---
        if max_score < 1.0:
            # Rate of change
            prev = self._previous_readings.get(machine_type, {})
            prev_ts = self._previous_timestamps.get(machine_type)
            if prev and prev_ts:
                elapsed = (timestamp - prev_ts).total_seconds()
                if elapsed > 0:
                    roc_results = self.physics.check_rate_of_change(
                        machine_type, readings, prev, elapsed
                    )
                    for r in roc_results:
                        if r.triggered:
                            explanations.append(f"PHYSICS: {r.description}")
                            all_contributing[r.rule_name] = 0.8
                            if 0.8 > max_score:
                                max_score = 0.8
                                fired_layer = 'physics'

            # Stuck sensor
            if recent_values:
                stuck_results = self.physics.check_stuck_sensor(machine_type, recent_values)
                for r in stuck_results:
                    if r.triggered:
                        explanations.append(f"PHYSICS: {r.description}")
                        all_contributing[r.rule_name] = 0.7
                        if 0.7 > max_score:
                            max_score = 0.7
                            fired_layer = 'physics'

            # Cross-sensor consistency
            cross_results = self.physics.check_cross_sensor(machine_type, readings)
            for r in cross_results:
                if r.triggered:
                    explanations.append(f"PHYSICS: {r.description}")
                    all_contributing[r.rule_name] = 0.7
                    if 0.7 > max_score:
                        max_score = 0.7
                        fired_layer = 'physics'

        # --- Layer 3: ML detection (only if no higher layer fired) ---
        ml_score = 0.0
        ml_anomaly = False
        ml_explanation = ''
        if max_score < 0.7:
            detector = get_detector()
            detection = detector.detect(machine_type, readings, timestamp)
            ml_score = detection.anomaly_score
            ml_anomaly = detection.is_anomaly
            if ml_anomaly and ml_score > max_score:
                max_score = ml_score
                ml_explanation = detection.explanation
                all_contributing.update(detection.contributing_sensors)
                fired_layer = 'ml'
            elif not ml_anomaly:
                ml_explanation = detection.explanation

        # --- Build final explanation ---
        if fired_layer == 'hard_limit':
            explanation = "Hard safety limit breached — " + "; ".join(e for e in explanations if e.startswith("SAFETY"))
        elif fired_layer == 'physics':
            explanation = "Physics plausibility violation — " + "; ".join(e for e in explanations if e.startswith("PHYSICS"))
        elif fired_layer == 'ml':
            explanation = f"ML anomaly detected — {ml_explanation}"
        else:
            explanation = "All checks normal — " + (ml_explanation or "No anomalies detected")

        is_anomaly = max_score >= 0.7
        confidence = max_score if is_anomaly else 1.0 - ml_score

        return Detection(
            is_anomaly=is_anomaly,
            anomaly_score=max_score,
            detector=f'explainable_{fired_layer}',
            explanation=explanation,
            contributing_sensors=all_contributing,
            confidence=confidence,
            timestamp=timestamp,
        )

    def update_history(self, machine_type: str, readings: Dict[str, float],
                       timestamp: datetime) -> None:
        """Update the reading history for rate-of-change and stuck detection.

        Call this after each detection cycle to maintain state.
        """
        self._previous_readings[machine_type] = readings.copy()
        self._previous_timestamps[machine_type] = timestamp

        if machine_type not in self._recent_values:
            self._recent_values[machine_type] = {}

        for sensor, value in readings.items():
            if sensor not in self._recent_values[machine_type]:
                self._recent_values[machine_type][sensor] = []
            self._recent_values[machine_type][sensor].append(value)
            # Keep only last STUCK_WINDOW_SIZE * 2 values for buffer
            if len(self._recent_values[machine_type][sensor]) > STUCK_WINDOW_SIZE * 2:
                self._recent_values[machine_type][sensor] = \
                    self._recent_values[machine_type][sensor][-STUCK_WINDOW_SIZE * 2:]

    def get_recent_values(self, machine_type: str) -> Dict[str, List[float]]:
        """Get recent values for stuck-sensor detection."""
        return self._recent_values.get(machine_type, {})


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_explainable_detector: Optional[ExplainableDetector] = None


def get_explainable_detector() -> ExplainableDetector:
    global _explainable_detector
    if _explainable_detector is None:
        _explainable_detector = ExplainableDetector()
    return _explainable_detector


def detect_explainable(machine_type: str, readings: Dict[str, float],
                       timestamp: Optional[datetime] = None) -> Detection:
    """Convenience function for explainable detection."""
    detector = get_explainable_detector()
    recent = detector.get_recent_values(machine_type)
    detection = detector.detect(machine_type, readings, timestamp, recent)
    detector.update_history(machine_type, readings, timestamp or datetime.utcnow())
    return detection
