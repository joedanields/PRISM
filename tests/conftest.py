"""Shared fixtures for PRISM test suite."""

import os
import sys
import pytest

# Ensure project root is on sys.path so `import config`, `import app`, etc. work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force demo .env before importing config (so _require doesn't exit)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("EMAIL_USER", "test@example.com")
os.environ.setdefault("EMAIL_PASSWORD", "test-password-0000")
os.environ.setdefault("EMAIL_MAINTENANCE_TEAM", "maint@example.com")
os.environ.setdefault("EMAIL_PLANT_MANAGER", "mgr@example.com")
os.environ.setdefault("EMAIL_EMERGENCY_RESPONSE", "emer@example.com")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "00000000000000000000000000000000")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("TWILIO_EMERGENCY_CONTACTS", "+15550000001,+15550000002")


@pytest.fixture()
def app_instance():
    """Create a fresh Flask app with an in-memory SQLite DB for each test."""
    from app import app
    from app import db as _db

    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SERVER_NAME"] = "localhost"

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app_instance):
    """Flask test client."""
    return app_instance.test_client()


@pytest.fixture()
def db_session(app_instance):
    """SQLAlchemy session scoped to a single test."""
    from app import db as _db

    with app_instance.app_context():
        yield _db.session
