"""Characterization tests for the anomaly detection engine.

These tests capture the CURRENT behaviour of detect_simple_anomaly() so we can
verify the F1 refactor doesn't change semantics.  Each test documents the rule
it exercises.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force env before importing config
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

from app import detect_simple_anomaly


# ---------------------------------------------------------------------------
# Fixtures: reusable sensor configs matching MACHINES_CONFIG
# ---------------------------------------------------------------------------
REACTOR_TEMP = {
    "min": 200, "max": 800, "unit": "°C",
    "normal_range": [250, 400],
}

REACTOR_PRESSURE = {
    "min": 1, "max": 50, "unit": "bar",
    "normal_range": [10, 30],
}


# ---------------------------------------------------------------------------
# Normal range tests
# ---------------------------------------------------------------------------
class TestNormalRange:
    """Values inside [normal_min, normal_max] should NOT be anomalies."""

    def test_value_at_center(self):
        is_anomaly, score = detect_simple_anomaly(325, REACTOR_TEMP, "normal")
        assert is_anomaly is False
        assert score == 0.0

    def test_value_at_lower_bound(self):
        is_anomaly, score = detect_simple_anomaly(250, REACTOR_TEMP, "normal")
        assert is_anomaly is False
        assert score == 0.0

    def test_value_at_upper_bound(self):
        is_anomaly, score = detect_simple_anomaly(400, REACTOR_TEMP, "normal")
        assert is_anomaly is False
        assert score == 0.0


# ---------------------------------------------------------------------------
# Below-range tests
# ---------------------------------------------------------------------------
class TestBelowRange:
    """Values below normal_min — deviation = (normal_min - value) / range_width."""

    def test_slight_below(self):
        """249 is 1 unit below 250; range width = 150.  deviation = 1/150 ≈ 0.0067 < 0.1 → NOT anomaly."""
        is_anomaly, score = detect_simple_anomaly(249, REACTOR_TEMP, "normal")
        assert is_anomaly is False

    def test_below_threshold(self):
        """235 is 15 below 250; deviation = 15/150 = 0.1 → NOT anomaly (must be > 0.1)."""
        is_anomaly, score = detect_simple_anomaly(235, REACTOR_TEMP, "normal")
        assert is_anomaly is False

    def test_just_above_threshold(self):
        """234 is 16 below; deviation = 16/150 ≈ 0.1067 > 0.1 → IS anomaly."""
        is_anomaly, score = detect_simple_anomaly(234, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert 0.1 < score <= 0.2

    def test_far_below(self):
        """200 (absolute min): deviation = 50/150 ≈ 0.333."""
        is_anomaly, score = detect_simple_anomaly(200, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert 0.33 <= score <= 0.34

    def test_score_capped_at_1(self):
        """Value far below min should produce score capped at 1.0."""
        is_anomaly, score = detect_simple_anomaly(0, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert score == 1.0


# ---------------------------------------------------------------------------
# Above-range tests
# ---------------------------------------------------------------------------
class TestAboveRange:
    """Values above normal_max — deviation = (value - normal_max) / range_width."""

    def test_slight_above(self):
        """401 is 1 above 400; deviation = 1/150 ≈ 0.0067 < 0.1 → NOT anomaly."""
        is_anomaly, score = detect_simple_anomaly(401, REACTOR_TEMP, "normal")
        assert is_anomaly is False

    def test_above_threshold(self):
        """420 is 20 above; deviation = 20/150 ≈ 0.133 > 0.1 → IS anomaly."""
        is_anomaly, score = detect_simple_anomaly(420, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert 0.13 <= score <= 0.14

    def test_far_above(self):
        """800 (absolute max): deviation = 400/150 ≈ 2.667 → capped at 1.0."""
        is_anomaly, score = detect_simple_anomaly(800, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert score == 1.0


# ---------------------------------------------------------------------------
# Sabotage mode tests
# ---------------------------------------------------------------------------
class TestSabotageMode:
    """Sabotage overrides: if value >= 90% of max OR <= 110% of min → forced anomaly at 0.95."""

    def test_sabotage_near_max(self):
        """90% of 800 = 720.  At exactly 720 → forced anomaly."""
        is_anomaly, score = detect_simple_anomaly(720, REACTOR_TEMP, "sabotage")
        assert is_anomaly is True
        assert score == 0.95

    def test_sabotage_above_90pct(self):
        """750 > 720 → forced anomaly."""
        is_anomaly, score = detect_simple_anomaly(750, REACTOR_TEMP, "sabotage")
        assert is_anomaly is True
        assert score == 0.95

    def test_sabotage_near_min(self):
        """110% of 200 = 220.  At exactly 220 → forced anomaly."""
        is_anomaly, score = detect_simple_anomaly(220, REACTOR_TEMP, "sabotage")
        assert is_anomaly is True
        assert score == 0.95

    def test_sabotage_below_110pct(self):
        """210 < 220 → forced anomaly."""
        is_anomaly, score = detect_simple_anomaly(210, REACTOR_TEMP, "sabotage")
        assert is_anomaly is True
        assert score == 0.95

    def test_sabotage_within_normal(self):
        """Value in normal range during sabotage — still scored by normal rules, NOT forced."""
        is_anomaly, score = detect_simple_anomaly(325, REACTOR_TEMP, "sabotage")
        assert is_anomaly is False
        assert score == 0.0

    def test_sabotage_pressure_near_max(self):
        """Pressure sensor: 90% of 50 = 45.  At 46 → forced anomaly."""
        is_anomaly, score = detect_simple_anomaly(46, REACTOR_PRESSURE, "sabotage")
        assert is_anomaly is True
        assert score == 0.95


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_zero_value(self):
        is_anomaly, score = detect_simple_anomaly(0, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert score == 1.0

    def test_negative_value(self):
        is_anomaly, score = detect_simple_anomaly(-50, REACTOR_TEMP, "normal")
        assert is_anomaly is True
        assert score == 1.0

    def test_exactly_at_deviation_boundary(self):
        """deviation == 0.1 exactly → NOT anomaly (must be > 0.1)."""
        # normal_min=250, normal_max=400, range=150
        # need deviation = 0.1 → value = 250 - 0.1*150 = 235
        is_anomaly, score = detect_simple_anomaly(235, REACTOR_TEMP, "normal")
        assert is_anomaly is False
