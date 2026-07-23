"""Tests for F3 — Authentication, RBAC & audit logging.

Covers:
  - User model (create, password hashing, role checks)
  - AuditLog model
  - Login/logout/register routes
  - Auth-gated money/human endpoints
  - Role-based access control
"""

import sys
import os

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

from app import app, db, User, AuditLog, log_audit


def _create_user(session, username="testuser", role="viewer"):
    u = User(username=username, email=f"{username}@test.com", role=role)
    u.set_password("password123")
    session.add(u)
    session.commit()
    return u


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------
class TestUserModel:
    def test_create_user(self, db_session):
        u = _create_user(db_session)
        assert u.id is not None
        assert u.username == "testuser"
        assert u.role == "viewer"
        assert u.is_active_user is True

    def test_password_hashing(self, db_session):
        u = _create_user(db_session)
        assert u.check_password("password123") is True
        assert u.check_password("wrong") is False
        assert u.password_hash != "password123"

    def test_role_checks(self, db_session):
        admin = _create_user(db_session, username="admin", role="admin")
        viewer = _create_user(db_session, username="viewer", role="viewer")
        assert admin.has_role("admin")
        assert not viewer.has_role("admin")
        assert viewer.has_role("viewer", "operator")

    def test_to_dict(self, db_session):
        u = _create_user(db_session)
        d = u.to_dict()
        assert d["username"] == "testuser"
        assert d["role"] == "viewer"
        assert "password_hash" not in d

    def test_user_mixin_is_active(self, db_session):
        u = _create_user(db_session)
        assert u.is_active is True


# ---------------------------------------------------------------------------
# AuditLog model
# ---------------------------------------------------------------------------
class TestAuditLogModel:
    def test_create_audit_log(self, db_session):
        u = _create_user(db_session)
        log_audit("mode_change", "machine", 1, "Set to maintenance", user=u)
        entries = AuditLog.query.all()
        assert len(entries) == 1
        assert entries[0].action == "mode_change"
        assert entries[0].username == "testuser"

    def test_to_dict(self, db_session):
        log_audit("test_action", "test_target", details="detail")
        entry = AuditLog.query.first()
        d = entry.to_dict()
        assert d["action"] == "test_action"
        assert d["username"] == "system"

    def test_append_only_no_delete(self, db_session):
        log_audit("a", "t")
        log_audit("b", "t")
        assert AuditLog.query.count() == 2


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
class TestAuthRoutes:
    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"PRISM Login" in resp.data

    def test_register_page_renders(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        assert b"Create Account" in resp.data

    def test_register_creates_user(self, client, db_session):
        resp = client.post("/register", data={
            "username": "newuser",
            "email": "new@test.com",
            "password": "pass123",
        }, follow_redirects=False)
        assert resp.status_code == 302
        u = User.query.filter_by(username="newuser").first()
        assert u is not None
        assert u.role == "admin"  # first user gets admin

    def test_register_second_user_is_viewer(self, client, db_session):
        _create_user(db_session, username="existing")
        resp = client.post("/register", data={
            "username": "second",
            "email": "second@test.com",
            "password": "pass123",
        }, follow_redirects=False)
        assert resp.status_code == 302
        u = User.query.filter_by(username="second").first()
        assert u is not None
        assert u.role == "viewer"

    def test_login_success(self, client, db_session):
        _create_user(db_session, username="loginuser")
        resp = client.post("/login", data={
            "username": "loginuser",
            "password": "password123",
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_login_wrong_password(self, client, db_session):
        _create_user(db_session)
        resp = client.post("/login", data={
            "username": "testuser",
            "password": "wrong",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_logout(self, client, db_session):
        _create_user(db_session, username="logoutuser")
        client.post("/login", data={"username": "logoutuser", "password": "password123"})
        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302

    def test_unauthenticated_api_returns_401(self, client):
        resp = client.get("/api/emergency-call/1")
        assert resp.status_code == 401

    def test_unauthenticated_dashboard_renders(self, client):
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------
class TestRBAC:
    def test_viewer_cannot_access_emergency_call(self, client, db_session):
        viewer = _create_user(db_session, username="v", role="viewer")
        client.post("/login", data={"username": "v", "password": "password123"})
        resp = client.get("/api/emergency-call/1")
        assert resp.status_code == 403

    def test_operator_can_access_emergency_call(self, client, db_session, monkeypatch):
        op = _create_user(db_session, username="op", role="operator")
        client.post("/login", data={"username": "op", "password": "password123"})
        from app import config as _cfg
        original = _cfg.ENABLE_EMERGENCY_ENDPOINTS
        _cfg.ENABLE_EMERGENCY_ENDPOINTS = True
        try:
            resp = client.get("/api/emergency-call/1")
            assert resp.status_code != 403
        finally:
            _cfg.ENABLE_EMERGENCY_ENDPOINTS = original

    def test_viewer_cannot_access_debug_test_call(self, client, db_session):
        viewer = _create_user(db_session, username="v2", role="viewer")
        client.post("/login", data={"username": "v2", "password": "password123"})
        resp = client.get("/debug/test-call/emergency")
        assert resp.status_code == 403
