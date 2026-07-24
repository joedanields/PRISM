"""F6: Historical replay and scenario engine.

ReplayDriver — replays stored readings from the DB at configurable speed.
ScenarioEngine — generates synthetic fault-injection readings from JSON definitions.

Both produce Reading objects compatible with the IngestionPipeline (F4).
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ingestion.drivers import Reading


# ---------------------------------------------------------------------------
# ReplayDriver — re-read stored readings from DB
# ---------------------------------------------------------------------------

class ReplayDriver:
    """Replays historical sensor readings from the database at configurable speed.

    Reads a time window from sensor_readings, sorts by timestamp, and yields
    them as Reading objects with optional time-compression (1x..100x).
    """

    name: str = "replay"

    def __init__(self, start: datetime, end: datetime, speed: float = 1.0,
                 machine_id: Optional[int] = None):
        """
        Args:
            start: Start of the replay window (UTC).
            end: End of the replay window (UTC).
            speed: Playback multiplier (1.0 = real-time, 10.0 = 10x faster).
            machine_id: Optional filter to a single machine.
        """
        self.start = start
        self.end = end
        self.speed = max(0.1, min(speed, 100.0))
        self.machine_id = machine_id
        self._connected = False
        self._cursor = 0
        self._buffer: List[Reading] = []
        self._replay_start_wall: Optional[float] = None

    def connect(self) -> None:
        from app import db, SensorReading
        query = SensorReading.query.filter(
            SensorReading.timestamp >= self.start,
            SensorReading.timestamp <= self.end,
        )
        if self.machine_id is not None:
            query = query.filter_by(machine_id=self.machine_id)
        rows = query.order_by(SensorReading.timestamp).all()

        self._buffer = [
            Reading(
                machine_ref=str(r.machine_id),
                sensor_type=r.sensor_type,
                value=r.value,
                unit=r.unit,
                timestamp=r.timestamp,
                source=f"replay({r.source or 'unknown'})",
                quality=r.quality or "good",
                is_anomaly=r.is_anomaly,
            )
            for r in rows
        ]
        self._cursor = 0
        self._replay_start_wall = time.monotonic()
        self._connected = True

    def read(self) -> Iterable[Reading]:
        if not self._connected:
            raise RuntimeError("ReplayDriver not connected")

        if self._cursor >= len(self._buffer):
            return []

        now_wall = time.monotonic()
        elapsed_wall = now_wall - self._replay_start_wall
        elapsed_replay = elapsed_wall * self.speed

        # How far into the replay time have we consumed?
        if self._cursor == 0:
            replay_start_ts = self._buffer[0].timestamp

        current_replay_ts = self._buffer[0].timestamp + timedelta(seconds=elapsed_replay)

        batch: List[Reading] = []
        while self._cursor < len(self._buffer):
            r = self._buffer[self._cursor]
            if r.timestamp <= current_replay_ts:
                batch.append(r)
                self._cursor += 1
            else:
                break

        return batch

    def close(self) -> None:
        self._connected = False

    @property
    def progress(self) -> float:
        """Return 0.0..1.0 progress through the replay buffer."""
        if not self._buffer:
            return 1.0
        return self._cursor / len(self._buffer)

    @property
    def total_readings(self) -> int:
        return len(self._buffer)


# ---------------------------------------------------------------------------
# ScenarioEngine — scripted fault injection
# ---------------------------------------------------------------------------

# Default scenario directory (relative to project root)
SCENARIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scenarios")

# Built-in fault patterns
FAULT_PATTERNS = {
    "sensor_drift": {
        "description": "Gradual upward drift on a sensor over time",
        "params": {"drift_rate": 0.5, "duration_seconds": 300},
    },
    "sudden_spike": {
        "description": "Sudden jump to extreme value, then return",
        "params": {"spike_multiplier": 2.5, "spike_duration": 10},
    },
    "stuck_at": {
        "description": "Sensor stuck at a fixed value (frozen transmitter)",
        "params": {"freeze_duration": 120},
    },
    "bearing_degradation": {
        "description": "Progressive vibration increase simulating bearing wear",
        "params": {"degradation_rate": 0.3, "duration_seconds": 600},
    },
    "intermittent_fault": {
        "description": "Random spikes at increasing frequency",
        "params": {"base_interval": 30, "frequency_increase": 0.1},
    },
}


@dataclass
class ScenarioStep:
    """A single step in a scenario timeline."""
    time_offset: float          # seconds from scenario start
    machine_type: str           # which machine type to affect
    sensor_type: str            # which sensor to inject fault on
    fault_pattern: str          # name of FAULT_PATTERNS entry
    params: Dict                # override params from FAULT_PATTERNS


@dataclass
class Scenario:
    """A complete fault-injection scenario."""
    name: str
    description: str
    version: str
    duration_seconds: float
    steps: List[ScenarioStep]
    target_machine_id: Optional[int] = None  # if set, inject into this machine

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "duration_seconds": self.duration_seconds,
            "target_machine_id": self.target_machine_id,
            "steps": [
                {
                    "time_offset": s.time_offset,
                    "machine_type": s.machine_type,
                    "sensor_type": s.sensor_type,
                    "fault_pattern": s.fault_pattern,
                    "params": s.params,
                }
                for s in self.steps
            ],
        }


class ScenarioEngine:
    """Generates synthetic readings from a Scenario definition.

    Produces Reading objects with faults injected according to the timeline.
    Base readings are generated from the SimulatorDriver's normal ranges.
    """

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self._start_time: Optional[datetime] = None

    def start(self) -> None:
        """Mark the scenario start time."""
        self._start_time = datetime.utcnow()

    def generate_batch(self, elapsed_seconds: float) -> List[Reading]:
        """Generate readings for the current elapsed time in the scenario.

        Args:
            elapsed_seconds: seconds since scenario start.

        Returns:
            List of Reading objects with normal values + injected faults.
        """
        if self._start_time is None:
            self.start()

        now = self._start_time + timedelta(seconds=elapsed_seconds)
        readings: List[Reading] = []

        # Determine which faults are active at this time offset
        active_faults: Dict[str, float] = {}  # sensor_key → fault_magnitude
        for step in self.scenario.steps:
            fault = FAULT_PATTERNS.get(step.fault_pattern)
            if fault is None:
                continue
            duration = step.params.get("duration_seconds", fault["params"].get("duration_seconds", 300))
            if step.time_offset <= elapsed_seconds <= step.time_offset + duration:
                fault_elapsed = elapsed_seconds - step.time_offset
                magnitude = self._compute_fault_magnitude(
                    step.fault_pattern, step.params, fault_elapsed, duration
                )
                key = f"{step.machine_type}:{step.sensor_type}"
                # Stack multiple faults on the same sensor
                active_faults[key] = active_faults.get(key, 0.0) + magnitude

        # Generate readings for all configured machine types
        for machine_type, config in _get_sensor_config().items():
            for sensor_type, sensor_cfg in config["sensors"].items():
                # Normal value
                base = random.uniform(*sensor_cfg["normal_range"])
                value = base + random.uniform(-0.02, 0.02) * base  # 2% noise

                # Apply fault if active
                key = f"{machine_type}:{sensor_type}"
                if key in active_faults:
                    value += active_faults[key]
                    # Clamp to sensor min/max
                    value = max(sensor_cfg["min"], min(sensor_cfg["max"], value))

                is_anomaly = self._check_anomaly(value, sensor_cfg)

                readings.append(Reading(
                    machine_ref=str(self.scenario.target_machine_id or 0),
                    sensor_type=sensor_type,
                    value=round(value, 2),
                    unit=sensor_cfg["unit"],
                    timestamp=now,
                    source=f"scenario:{self.scenario.name}",
                    quality="good",
                    is_anomaly=is_anomaly,
                ))

        return readings

    def _compute_fault_magnitude(self, pattern: str, params: dict,
                                  fault_elapsed: float, duration: float) -> float:
        """Calculate the fault magnitude at a given point in time."""
        if pattern == "sensor_drift":
            rate = params.get("drift_rate", 0.5)
            return rate * fault_elapsed
        elif pattern == "sudden_spike":
            spike_dur = params.get("spike_duration", 10)
            if fault_elapsed <= spike_dur:
                return params.get("spike_multiplier", 2.5) * 100
            return 0
        elif pattern == "stuck_at":
            # Return a fixed offset — combined with base noise, simulates frozen sensor
            return 50  # fixed offset from normal center
        elif pattern == "bearing_degradation":
            rate = params.get("degradation_rate", 0.3)
            # Non-linear: exponential increase
            return rate * fault_elapsed * (1 + fault_elapsed / duration)
        elif pattern == "intermittent_fault":
            base_interval = params.get("base_interval", 30)
            freq_inc = params.get("frequency_increase", 0.1)
            # Increasing frequency of spikes
            interval = max(1.0, base_interval - freq_inc * fault_elapsed)
            if int(fault_elapsed) % int(interval) == 0:
                return random.uniform(50, 150)
            return 0
        return 0

    def _check_anomaly(self, value: float, sensor_cfg: dict) -> bool:
        """Check if a value is anomalous given sensor config."""
        normal_min, normal_max = sensor_cfg["normal_range"]
        if value < normal_min:
            deviation = (normal_min - value) / (normal_max - normal_min)
        elif value > normal_max:
            deviation = (value - normal_max) / (normal_max - normal_min)
        else:
            deviation = 0
        return deviation > 0.1


# ---------------------------------------------------------------------------
# Scenario file I/O
# ---------------------------------------------------------------------------

def load_scenario(path: str) -> Scenario:
    """Load a scenario from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    steps = [
        ScenarioStep(
            time_offset=s["time_offset"],
            machine_type=s["machine_type"],
            sensor_type=s["sensor_type"],
            fault_pattern=s["fault_pattern"],
            params=s.get("params", {}),
        )
        for s in data.get("steps", [])
    ]
    return Scenario(
        name=data["name"],
        description=data.get("description", ""),
        version=data.get("version", "1.0"),
        duration_seconds=data["duration_seconds"],
        steps=steps,
        target_machine_id=data.get("target_machine_id"),
    )


def save_scenario(scenario: Scenario, path: str) -> None:
    """Save a scenario to a JSON file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(scenario.to_dict(), f, indent=2)


def list_scenarios(directory: str = SCENARIO_DIR) -> List[str]:
    """List all scenario JSON files in a directory."""
    if not os.path.isdir(directory):
        return []
    return sorted(
        f for f in os.listdir(directory)
        if f.endswith(".json")
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_sensor_config_cache = None

def _get_sensor_config():
    global _sensor_config_cache
    if _sensor_config_cache is None:
        from models.data_generator import MACHINES_CONFIG
        _sensor_config_cache = MACHINES_CONFIG
    return _sensor_config_cache
