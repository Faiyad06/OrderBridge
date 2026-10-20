"""Opaque expiring server sessions with CSRF tokens. Actor/tenant/role derive from the session only."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import bcrypt

from .. import config
from ..db import audit, clock, get_conn, write_tx
from .errors import Actor, AppError


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10)).decode()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(username: str, password: str) -> tuple[str, str, Actor]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    # Constant-ish work even for unknown users
    hashed = row["password_hash"].encode() if row else bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=10))
    ok = bcrypt.checkpw(password.encode(), hashed)
    if not row or not ok:
        raise AppError("UNAUTHENTICATED", "Invalid username or password.", 401)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = clock.now()
    mode = "live" if config.anthropic_key_configured() else "replay"
    with write_tx(conn):
        conn.execute("INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, expires_at, agent_mode) VALUES (?,?,?,?,?,?)",
                     (_token_hash(token), row["user_id"], csrf, now.isoformat(), (now + timedelta(seconds=config.SESSION_TTL_SECONDS)).isoformat(), mode))
        audit(conn, row["tenant_id"], "user", row["user_id"], "login")
    return token, csrf, _actor(row, _token_hash(token), mode)


def _actor(row, token_hash: str | None, mode: str) -> Actor:
    return Actor(user_id=row["user_id"], tenant_id=row["tenant_id"], role=row["role"], username=row["username"],
                 display_name=row["display_name"], session_token_hash=token_hash, agent_mode=mode)


def session_actor(token: str | None) -> tuple[Actor, str]:
    if not token:
        raise AppError("UNAUTHENTICATED", "Sign in required.", 401)
    conn = get_conn()
    th = _token_hash(token)
    s = conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (th,)).fetchone()
    if not s or datetime.fromisoformat(s["expires_at"]) <= clock.now():
        raise AppError("UNAUTHENTICATED", "Session expired or invalid. Sign in again.", 401)
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (s["user_id"],)).fetchone()
    return _actor(u, th, s["agent_mode"]), s["csrf_token"]


def check_csrf(expected: str, provided: str | None) -> None:
    if not provided or not hmac.compare_digest(expected, provided):
        raise AppError("CSRF_FAILED", "Missing or invalid CSRF token.", 403)


def logout(actor: Actor) -> None:
    conn = get_conn()
    with write_tx(conn):
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (actor.session_token_hash,))
        audit(conn, actor.tenant_id, "user", actor.user_id, "logout")


def set_agent_mode(actor: Actor, mode: str) -> None:
    if mode not in ("live", "replay"):
        raise AppError("VALIDATION_ERROR", "mode must be 'live' or 'replay'.")
    conn = get_conn()
    with write_tx(conn):
        conn.execute("UPDATE sessions SET agent_mode = ? WHERE token_hash = ?", (mode, actor.session_token_hash))
        audit(conn, actor.tenant_id, "user", actor.user_id, "agent_mode_changed", detail={"mode": mode})
