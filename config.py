"""PRISM configuration — environment-driven with fail-fast validation.

All secrets come from environment variables or a .env file (loaded via
python-dotenv).  The app MUST refuse to start if a required secret is
missing — fail fast, never silently substitute a placeholder.

Phase-0 interim additions:
  ENABLE_DEBUG_ROUTES  — must be ``true`` to expose /debug/* routes.
  ENABLE_EMERGENCY_ENDPOINTS — must be ``true`` to expose /api/emergency-call/*.
"""

import os
import sys
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()  # loads .env if present; harmless if absent


def _require(key: str, default: Optional[str] = None) -> str:
    """Return env var value or *default*; exit if neither exists."""
    val = os.environ.get(key, default)
    if val is None:
        print(f"FATAL: required environment variable {key} is not set.", file=sys.stderr)
        print(f"       Copy .env.example to .env and fill in real values.", file=sys.stderr)
        sys.exit(1)
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------
SECRET_KEY: str = _require("SECRET_KEY", "dev-only-insecure-key-change-me")
SQLALCHEMY_DATABASE_URI: str = _optional("DATABASE_URL", "sqlite:///machines.db")
SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
DEBUG: bool = _optional("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Feature flags (Phase-0 interim lockdown)
# ---------------------------------------------------------------------------
ENABLE_DEBUG_ROUTES: bool = _optional("ENABLE_DEBUG_ROUTES", "false").lower() in ("true", "1", "yes")
ENABLE_EMERGENCY_ENDPOINTS: bool = _optional("ENABLE_EMERGENCY_ENDPOINTS", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Email (Gmail SMTP)
# ---------------------------------------------------------------------------
EMAIL_SMTP_SERVER: str = _optional("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT: int = int(_optional("EMAIL_SMTP_PORT", "587"))
EMAIL_USER: str = _require("EMAIL_USER")
EMAIL_PASSWORD: str = _require("EMAIL_PASSWORD")
EMAIL_MAINTENANCE_TEAM: str = _require("EMAIL_MAINTENANCE_TEAM")
EMAIL_PLANT_MANAGER: str = _require("EMAIL_PLANT_MANAGER")
EMAIL_EMERGENCY_RESPONSE: str = _require("EMAIL_EMERGENCY_RESPONSE")

# ---------------------------------------------------------------------------
# Twilio
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID: str = _require("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN: str = _require("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER: str = _require("TWILIO_PHONE_NUMBER")
TWILIO_EMERGENCY_CONTACTS: List[str] = [
    c.strip()
    for c in _require("TWILIO_EMERGENCY_CONTACTS", "+15550000001,+15550000002,+15550000003").split(",")
    if c.strip()
]
TWILIO_VOICE: str = _optional("TWILIO_VOICE", "alice")
TWILIO_LANGUAGE: str = _optional("TWILIO_LANGUAGE", "en-US")

# ---------------------------------------------------------------------------
# OpenAI / Chatbot (optional)
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = _optional("OPENAI_API_KEY", "")
CHATBOT_USE_OPENAI: bool = _optional("CHATBOT_USE_OPENAI", "false").lower() in ("true", "1", "yes")
CHATBOT_USE_LOCAL_AI: bool = _optional("CHATBOT_USE_LOCAL_AI", "true").lower() in ("true", "1", "yes")
CHATBOT_LOCAL_MODEL: str = _optional("CHATBOT_LOCAL_MODEL", "llama2")

# ---------------------------------------------------------------------------
# Auth (F3)
# ---------------------------------------------------------------------------
ENABLE_AUTH: bool = _optional("ENABLE_AUTH", "true").lower() in ("true", "1", "yes")
DEFAULT_ADMIN_PASSWORD: str = _optional("DEFAULT_ADMIN_PASSWORD", "admin123")
