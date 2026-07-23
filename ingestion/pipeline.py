"""Ingestion pipeline — takes Reading objects from any driver and persists them.

F4: Normalizes, validates, and writes to the DB. Handles bad quality flags,
driver failures, and triggers alert generation for anomalies.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from ingestion.drivers import Reading

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Receives Reading objects from a driver and writes them to the database.

    Supports optional tag mapping (external refs → machine_id) and
    quality filtering (skip bad readings).
    """

    def __init__(self, tag_map: Optional[dict] = None, reject_bad_quality: bool = True):
        """
        Args:
            tag_map: Dict mapping external machine_ref strings to integer machine_ids.
                     If None, machine_ref is treated as the machine_id directly.
            reject_bad_quality: If True, readings with quality="bad" are skipped.
        """
        self.tag_map = tag_map or {}
        self.reject_bad_quality = reject_bad_quality
        self._stats = {"ingested": 0, "skipped_quality": 0, "errors": 0}

    def ingest(self, readings: List[Reading]) -> dict:
        """Persist a batch of readings to the database.

        Returns:
            Dict with ingestion stats: ingested, skipped_quality, errors.
        """
        from app import db, SensorReading, Machine

        stats = {"ingested": 0, "skipped_quality": 0, "errors": 0}
        critical_anomalies = []  # (machine_id, sensor_type, value, unit)

        for reading in readings:
            # Quality gate
            if self.reject_bad_quality and reading.quality == "bad":
                stats["skipped_quality"] += 1
                logger.debug("Skipping bad-quality reading: %s/%s", reading.machine_ref, reading.sensor_type)
                continue

            # Resolve machine_ref → machine_id
            machine_id = self._resolve_machine(reading.machine_ref)
            if machine_id is None:
                stats["errors"] += 1
                logger.warning("Unknown machine_ref: %s", reading.machine_ref)
                continue

            try:
                sr = SensorReading(
                    machine_id=machine_id,
                    sensor_type=reading.sensor_type,
                    value=reading.value,
                    unit=reading.unit,
                    is_anomaly=reading.is_anomaly,
                    anomaly_score=1.0 if reading.is_anomaly else 0.0,
                    timestamp=reading.timestamp,
                    source=reading.source,
                )
                db.session.add(sr)
                stats["ingested"] += 1

                if reading.is_anomaly and sr.anomaly_score > 0.8:
                    critical_anomalies.append((machine_id, reading.sensor_type, reading.value, reading.unit))

            except Exception as e:
                stats["errors"] += 1
                logger.error("Failed to ingest reading: %s", e)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            stats["errors"] += 1
            logger.error("Batch commit failed: %s", e)

        # Generate alerts for critical anomalies
        if critical_anomalies:
            self._generate_alerts(critical_anomalies)

        self._stats = {k: self._stats[k] + stats[k] for k in stats}
        return stats

    def get_stats(self) -> dict:
        return dict(self._stats)

    def _resolve_machine(self, machine_ref: str) -> Optional[int]:
        """Map external machine_ref to internal machine_id."""
        if machine_ref in self.tag_map:
            return self.tag_map[machine_ref]
        try:
            return int(machine_ref)
        except (ValueError, TypeError):
            return None

    def _generate_alerts(self, anomalies: list) -> None:
        """Create Alert records for critical anomalies."""
        from app import db, Alert

        # Group by machine_id
        by_machine = {}
        for machine_id, sensor_type, value, unit in anomalies:
            by_machine.setdefault(machine_id, []).append((sensor_type, value, unit))

        for machine_id, readings_list in by_machine.items():
            try:
                alert = Alert(
                    machine_id=machine_id,
                    alert_type="critical",
                    severity="critical",
                    title=f"CRITICAL: Machine {machine_id} Emergency!",
                    message=(
                        "Critical sensor anomalies detected! Sensors: "
                        + ", ".join(f"{s}={v:.1f}{u}" for s, v, u in readings_list)
                        + ". IMMEDIATE ACTION REQUIRED!"
                    ),
                    sensor_data=json.dumps(
                        [{"sensor": s, "value": v, "unit": u} for s, v, u in readings_list]
                    ),
                )
                db.session.add(alert)
                db.session.commit()
                logger.critical("Alert created for machine %d: %d anomalies", machine_id, len(readings_list))
            except Exception as e:
                db.session.rollback()
                logger.error("Failed to create alert for machine %d: %s", machine_id, e)
