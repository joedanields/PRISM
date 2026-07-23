"""Simulator driver — wraps existing PRISM data generation as a SensorDriver.

F4: Makes the built-in simulator just one pluggable driver among many.
"""

from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Iterable, List

from ingestion.drivers import Reading

# Re-export the existing config and helpers so the simulator driver is self-contained.
# Import is deferred to avoid circular deps at module level.
_MACHINES_CONFIG = None


def _get_config():
    global _MACHINES_CONFIG
    if _MACHINES_CONFIG is None:
        from models.data_generator import MACHINES_CONFIG
        _MACHINES_CONFIG = MACHINES_CONFIG
    return _MACHINES_CONFIG


class SimulatorDriver:
    """Produces synthetic sensor readings that mimic real industrial machines.

    Implements the SensorDriver protocol. Reads are generated in-memory
    and returned as Reading objects — the pipeline handles DB persistence.
    """

    name: str = "simulator"

    def __init__(self):
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def read(self) -> Iterable[Reading]:
        if not self._connected:
            raise RuntimeError("SimulatorDriver not connected; call connect() first")

        from app import db, Machine

        machines = Machine.query.filter_by(is_active=True).all()
        config = _get_config()
        now = datetime.utcnow()
        readings: List[Reading] = []

        for machine in machines:
            machine_cfg = config.get(machine.machine_type)
            if not machine_cfg:
                continue
            for sensor_type, sensor_cfg in machine_cfg["sensors"].items():
                value = _generate_value(sensor_cfg, machine.status)
                is_anomaly, _anomaly_score = _detect_anomaly(sensor_cfg, value, machine.status)

                readings.append(Reading(
                    machine_ref=str(machine.id),
                    sensor_type=sensor_type,
                    value=round(value, 2),
                    unit=sensor_cfg["unit"],
                    timestamp=now,
                    source=self.name,
                    quality="good",
                    is_anomaly=is_anomaly,
                ))

        return readings

    def close(self) -> None:
        self._connected = False


# ---------------------------------------------------------------------------
# Internal helpers (ported from models/data_generator.py)
# ---------------------------------------------------------------------------

def _generate_value(sensor_cfg: dict, machine_status: str) -> float:
    min_val = sensor_cfg["min"]
    max_val = sensor_cfg["max"]
    normal_min, normal_max = sensor_cfg["normal_range"]

    if machine_status == "normal":
        base = random.uniform(normal_min, normal_max)
        noise = random.uniform(-0.02, 0.02) * base
        return max(min_val, min(max_val, base + noise))
    elif machine_status == "maintenance":
        base = random.uniform(normal_min, normal_max)
        if random.random() < 0.4:
            dev = random.uniform(0.15, 0.35) * (normal_max - normal_min)
            base += random.choice([-dev, dev])
        return max(min_val, min(max_val, base))
    elif machine_status == "sabotage":
        if random.random() < 0.8:
            if random.random() < 0.5:
                return random.uniform(max_val * 0.85, max_val)
            else:
                return random.uniform(min_val, min_val + (max_val - min_val) * 0.15)
        return random.uniform(normal_min, normal_max)
    elif machine_status == "shutdown":
        return min_val + (max_val - min_val) * 0.05
    return random.uniform(normal_min, normal_max)


def _detect_anomaly(sensor_cfg: dict, value: float, machine_status: str) -> tuple:
    normal_min, normal_max = sensor_cfg["normal_range"]
    if value < normal_min:
        deviation = (normal_min - value) / (normal_max - normal_min)
    elif value > normal_max:
        deviation = (value - normal_max) / (normal_max - normal_min)
    else:
        deviation = 0.0

    is_anomaly = deviation > 0.1
    anomaly_score = min(1.0, deviation)

    if machine_status == "sabotage":
        if value >= sensor_cfg["max"] * 0.9 or value <= sensor_cfg["min"] * 1.1:
            is_anomaly = True
            anomaly_score = 0.95

    return is_anomaly, anomaly_score
