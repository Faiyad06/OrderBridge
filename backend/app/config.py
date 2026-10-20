"""Server-side configuration. Secrets come only from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT_DIR / "fixtures"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def _load_dotenv() -> None:
    env = ROOT_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DB_PATH = Path(os.environ.get("ORDERBRIDGE_DB", ROOT_DIR / "data" / "orderbridge.sqlite3"))
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
ANTHROPIC_FALLBACKS = os.environ.get("ANTHROPIC_FALLBACKS", "default")  # "off" disables server-side refusal fallback
SESSION_TTL_SECONDS = int(os.environ.get("ORDERBRIDGE_SESSION_TTL", "28800"))
SECURE_COOKIES = os.environ.get("ORDERBRIDGE_SECURE_COOKIES", "0") == "1"
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get(
    "ORDERBRIDGE_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()}

# Proposed prototype policy (not legal or bank requirements)
POLICY = {
    "policy_version": "demo-policy-1",
    "per_payment_limit_minor": 100_000_00,
    "daily_outgoing_limit_minor": 120_000_00,
    "min_account_buffer_minor": 20_000_00,
    "approval_ttl_seconds": 600,
    "currency": "CNY",
}

AGENT_BUDGET = {"max_model_turns": 8, "max_tool_calls": 12, "request_timeout_seconds": 60, "max_request_chars": 200_000}


def anthropic_key_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
