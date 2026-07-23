"""Core ingestion contracts — SensorDriver protocol and Reading dataclass.

F4: Any data source (simulator, MQTT, OPC-UA, Modbus) implements SensorDriver.
The pipeline normalizes all readings into the common Reading shape before persisting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Protocol, runtime_checkable


@dataclass
class Reading:
    """Normalized sensor reading produced by any driver.

    Attributes:
        machine_ref: External tag/topic/identifier — resolved to machine_id by the pipeline.
        sensor_type: Sensor category (e.g. "temperature", "pressure").
        value: Numeric reading.
        unit: Engineering unit (e.g. "°C", "bar").
        timestamp: When the reading was taken (UTC).
        source: Driver name that produced this reading.
        quality: Data quality from the source — "good", "uncertain", or "bad".
        is_anomaly: Whether the driver itself flagged this as anomalous (optional hint).
    """

    machine_ref: str
    sensor_type: str
    value: float
    unit: str
    timestamp: datetime
    source: str
    quality: str = "good"
    is_anomaly: bool = False

    def __post_init__(self):
        if self.quality not in ("good", "uncertain", "bad"):
            raise ValueError(f"Invalid quality '{self.quality}'; must be good|uncertain|bad")
        if math.isnan(self.value) or math.isinf(self.value):
            raise ValueError(f"Invalid value {self.value}; must be finite")


@runtime_checkable
class SensorDriver(Protocol):
    """Protocol that all sensor data drivers must implement.

    A driver connects to a data source, yields Reading objects on read(),
    and cleans up on close(). Drivers must be safe to instantiate but
    should not connect in __init__ — call connect() explicitly.
    """

    name: str

    def connect(self) -> None:
        """Establish connection to the data source."""
        ...

    def read(self) -> Iterable[Reading]:
        """Yield a batch of readings from the source.

        Called repeatedly by the ingestion pipeline. Each call should return
        new readings since the last call (or an empty iterable if none available).
        """
        ...

    def close(self) -> None:
        """Release resources and disconnect."""
        ...
