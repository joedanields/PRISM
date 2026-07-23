"""SSE stream module — generates Server-Sent Events for live dashboard.

F16: Provides an EventSource-compatible streaming endpoint that publishes
sensor readings, alerts, and health updates as they happen.

The stream polls the DB at a configurable interval (default 3s) and yields
only NEW data since the last check, minimizing bandwidth and DB load.
"""

from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timedelta
from typing import Generator, Optional

logger = logging.getLogger(__name__)


def generate_events(poll_interval: float = 3.0, machine_id: Optional[int] = None) -> Generator[str, None, None]:
    """Generator that yields SSE-formatted event strings.

    Yields events of types:
      - "reading": new sensor reading data
      - "alert": new or updated alert
      - "health": sensor health update
      - "heartbeat": keep-alive every poll_interval seconds

    Args:
        poll_interval: Seconds between DB polls (default 3.0).
        machine_id: If set, only stream events for this machine.

    Yields:
        SSE-formatted strings: "event: <type>\\ndata: <json>\\n\\n"
    """
    from app import db, SensorReading, Alert, SensorHealth, Machine

    last_reading_id = _get_max_id(SensorReading)
    last_alert_id = _get_max_id(Alert)
    last_health_update = datetime.utcnow()
    consecutive_empty = 0

    while True:
        try:
            from flask import current_app
            with current_app.app_context():
                events_found = False

                # New readings
                new_readings = _get_new_readings(last_reading_id, machine_id)
                if new_readings:
                    events_found = True
                    last_reading_id = max(r.id for r in new_readings)
                    # Batch readings by machine for efficiency
                    by_machine = {}
                    for r in new_readings:
                        by_machine.setdefault(r.machine_id, []).append({
                            'id': r.id,
                            'sensor_type': r.sensor_type,
                            'value': r.value,
                            'unit': r.unit,
                            'is_anomaly': r.is_anomaly,
                            'anomaly_score': r.anomaly_score,
                            'timestamp': r.timestamp.isoformat() if r.timestamp else None,
                            'source': r.source,
                        })
                    for mid, readings_list in by_machine.items():
                        yield _format_event('reading', {
                            'machine_id': mid,
                            'readings': readings_list,
                        })

                # New alerts
                new_alerts = _get_new_alerts(last_alert_id, machine_id)
                if new_alerts:
                    events_found = True
                    last_alert_id = max(a.id for a in new_alerts)
                    for alert in new_alerts:
                        yield _format_event('alert', {
                            'id': alert.id,
                            'machine_id': alert.machine_id,
                            'alert_type': alert.alert_type,
                            'severity': alert.severity,
                            'title': alert.title,
                            'message': alert.message,
                            'created_at': alert.created_at.isoformat() if alert.created_at else None,
                        })

                # Health updates (check every 10s to avoid thrashing)
                if datetime.utcnow() - last_health_update > timedelta(seconds=10):
                    health_updates = _get_health_updates(last_health_update, machine_id)
                    if health_updates:
                        events_found = True
                        for sh in health_updates:
                            yield _format_event('health', {
                                'machine_id': sh.machine_id,
                                'sensor_type': sh.sensor_type,
                                'health_percentage': sh.health_percentage,
                                'status': sh.status,
                            })
                    last_health_update = datetime.utcnow()

                # Heartbeat if no events (keeps connection alive)
                if not events_found:
                    consecutive_empty += 1
                    yield _format_event('heartbeat', {
                        'ts': datetime.utcnow().isoformat(),
                        'polls': consecutive_empty,
                    })
                else:
                    consecutive_empty = 0

        except GeneratorExit:
            logger.info("SSE client disconnected")
            return
        except Exception as e:
            logger.error("SSE stream error: %s", e)
            yield _format_event('error', {'message': str(e)})

        try:
            time.sleep(poll_interval)
        except (KeyboardInterrupt, SystemExit):
            return


def _format_event(event_type: str, data: dict) -> str:
    """Format a dict as an SSE message."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _get_max_id(model) -> int:
    """Get the highest ID currently in the table."""
    from app import db
    try:
        result = db.session.query(db.func.max(model.id)).scalar()
        return result or 0
    except Exception:
        return 0


def _get_new_readings(since_id: int, machine_id: Optional[int] = None):
    """Fetch readings with ID > since_id."""
    from app import db, SensorReading
    query = SensorReading.query.filter(SensorReading.id > since_id)
    if machine_id is not None:
        query = query.filter_by(machine_id=machine_id)
    return query.order_by(SensorReading.id).limit(100).all()


def _get_new_alerts(since_id: int, machine_id: Optional[int] = None):
    """Fetch alerts with ID > since_id."""
    from app import db, Alert
    query = Alert.query.filter(Alert.id > since_id)
    if machine_id is not None:
        query = query.filter_by(machine_id=machine_id)
    return query.order_by(Alert.id).limit(50).all()


def _get_health_updates(since: datetime, machine_id: Optional[int] = None):
    """Fetch health records updated since the given time."""
    from app import db, SensorHealth
    query = SensorHealth.query.filter(SensorHealth.last_updated > since)
    if machine_id is not None:
        query = query.filter_by(machine_id=machine_id)
    return query.all()
