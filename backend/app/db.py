"""SQLite persistence. Parameterised queries only; explicit transaction boundaries.

Write transactions use BEGIN IMMEDIATE so competing account writes are serialised
by SQLite's reserved lock (see docs/technical-design.md).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id), username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('owner','viewer')), display_name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id), csrf_token TEXT NOT NULL,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, agent_mode TEXT NOT NULL DEFAULT 'replay');
CREATE TABLE IF NOT EXISTS businesses (
  business_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL UNIQUE REFERENCES tenants(tenant_id), name TEXT NOT NULL,
  currency TEXT NOT NULL, timezone TEXT NOT NULL, opening_cash_minor INTEGER NOT NULL, opening_date TEXT NOT NULL,
  buffer_minor INTEGER NOT NULL, horizon_end TEXT NOT NULL, input_version INTEGER NOT NULL DEFAULT 1,
  order_json TEXT, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, label TEXT NOT NULL, sha256 TEXT NOT NULL, source_type TEXT NOT NULL,
  raw_text TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cash_events (
  tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, business_id TEXT NOT NULL, date TEXT, direction TEXT NOT NULL,
  amount_minor INTEGER, currency TEXT NOT NULL, category TEXT, counterparty_id TEXT, source_document_id TEXT, source_ref TEXT,
  confirmation_status TEXT NOT NULL, description TEXT, order_id TEXT, source_id TEXT, original_json TEXT NOT NULL,
  record_version INTEGER NOT NULL DEFAULT 1, created_in_version INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, event_id));
CREATE TABLE IF NOT EXISTS record_edits (
  edit_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, field TEXT NOT NULL,
  old_value TEXT, new_value TEXT, actor TEXT NOT NULL, ts TEXT NOT NULL, input_version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS imports (
  import_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, filename TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL,
  rows_json TEXT NOT NULL, base_version INTEGER NOT NULL, created_at TEXT NOT NULL, committed_version INTEGER, source_id TEXT,
  order_id TEXT);
CREATE TABLE IF NOT EXISTS scenario_conditions (
  tenant_id TEXT NOT NULL, condition_id TEXT NOT NULL, status TEXT NOT NULL, confirmed_by TEXT, confirmed_at TEXT, note TEXT,
  PRIMARY KEY (tenant_id, condition_id));
CREATE TABLE IF NOT EXISTS forecast_runs (
  run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, scenario_id TEXT NOT NULL, input_version INTEGER NOT NULL,
  account_version INTEGER, result_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counterparties (
  tenant_id TEXT NOT NULL, counterparty_id TEXT NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL, test_account TEXT,
  payment_allowlisted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (tenant_id, counterparty_id));
CREATE TABLE IF NOT EXISTS sandbox_accounts (
  account_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, currency TEXT NOT NULL, available_minor INTEGER NOT NULL,
  simulated_date TEXT NOT NULL, ledger_version INTEGER NOT NULL, scenario_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_sandbox ON sandbox_accounts(tenant_id) WHERE active = 1;
CREATE TABLE IF NOT EXISTS sandbox_ledger (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, tenant_id TEXT NOT NULL, simulated_date TEXT NOT NULL,
  delta_minor INTEGER NOT NULL, balance_after_minor INTEGER NOT NULL, reason TEXT NOT NULL, event_id TEXT, action_id TEXT, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settlements (
  settlement_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL, event_id TEXT NOT NULL, actual_date TEXT NOT NULL,
  amount_minor INTEGER NOT NULL, action_id TEXT, kind TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_settlement_per_action ON settlements(tenant_id, action_id) WHERE action_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, action_type TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
  state TEXT NOT NULL, idempotency_key TEXT NOT NULL, policy_checks_json TEXT NOT NULL, failure_code TEXT, failure_reason TEXT,
  receipt_json TEXT, prepared_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (tenant_id, idempotency_key));
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, action_id TEXT NOT NULL, actor_user_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
  policy_version TEXT NOT NULL, approved_at TEXT NOT NULL, expires_at TEXT NOT NULL, state TEXT NOT NULL,
  execution_capability_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, ts TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT,
  event_type TEXT NOT NULL, action_id TEXT, tool_name TEXT, decision_code TEXT, detail_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_runs (
  agent_run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, mode TEXT NOT NULL, task TEXT NOT NULL, status TEXT NOT NULL,
  transcript_json TEXT NOT NULL, envelope_json TEXT, created_at TEXT NOT NULL, elapsed_ms INTEGER);
"""


class Clock:
    """Injectable UTC clock so approval expiry can be tested without sleeping."""

    def __init__(self):
        self._offset_seconds = 0.0

    def now(self) -> datetime:
        from datetime import timedelta
        return datetime.now(timezone.utc) + timedelta(seconds=self._offset_seconds)

    def advance(self, seconds: float) -> None:
        self._offset_seconds += seconds


clock = Clock()


def utcnow_iso() -> str:
    return clock.now().isoformat(timespec="seconds")


_local = threading.local()


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path or config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_conn() -> sqlite3.Connection:
    key = str(config.DB_PATH)
    cache = getattr(_local, "conns", None)
    if cache is None:
        cache = _local.conns = {}
    if key not in cache:
        cache[key] = connect()
    return cache[key]


def reset_thread_connections() -> None:
    for c in getattr(_local, "conns", {}).values():
        c.close()
    _local.conns = {}


@contextmanager
def write_tx(conn: sqlite3.Connection):
    """Serialised write transaction (BEGIN IMMEDIATE)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def audit(conn: sqlite3.Connection, tenant_id: str, actor_type: str, actor_id: str | None, event_type: str, *,
          action_id: str | None = None, tool_name: str | None = None, decision_code: str | None = None, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_events (tenant_id, ts, actor_type, actor_id, event_type, action_id, tool_name, decision_code, detail_json) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (tenant_id, utcnow_iso(), actor_type, actor_id, event_type, action_id, tool_name, decision_code, json.dumps(detail or {}, sort_keys=True)),
    )
