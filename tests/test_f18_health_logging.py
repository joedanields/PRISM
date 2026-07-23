"""Tests for F18 — Health endpoints and structured logging.

Covers:
  - /healthz liveness probe
  - /readyz readiness probe
  - structured_logging module
"""

import sys
import os
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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

from app import app


class TestHealthEndpoints:
    def test_healthz_returns_200(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_readyz_returns_200(self, client):
        resp = client.get("/readyz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["components"]["database"] == "ok"
        assert data["status"] == "ready"


class TestStructuredLogging:
    def test_json_formatter(self):
        from structured_logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello %s", args=("world",), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello world"
        assert "timestamp" in parsed

    def test_text_formatter(self):
        from structured_logging import TextFormatter
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="test.py",
            lineno=1, msg="warning message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert "WARNING" in output
        assert "warning message" in output

    def test_setup_logging_json(self):
        from structured_logging import setup_logging
        setup_logging(log_format="json")
        root = logging.getLogger()
        assert len(root.handlers) > 0

    def test_setup_logging_text(self):
        from structured_logging import setup_logging
        setup_logging(log_format="text")
        root = logging.getLogger()
        assert len(root.handlers) > 0
