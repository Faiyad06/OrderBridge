"""Reproducible seed for the local demo. Run via scripts/reset_demo.py (never exposed as an HTTP route or LLM tool)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config
from .db import connect, init_schema, utcnow_iso
from .domain.money import parse_amount_minor
from .fixtures_loader import read_json
from .services.auth import hash_password

TENANT_A, TENANT_B = "tenant_gba", "tenant_other"


def demo_password() -> str:
    return os.environ.get("ORDERBRIDGE_DEMO_PASSWORD", "orderbridge-demo")


def seed(db_path: Path | None = None, *, load_example: bool = False) -> Path:
    path = Path(db_path or config.DB_PATH)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    conn = connect(path)
    init_schema(conn)
    b = read_json("business.json")
    pw = hash_password(demo_password())
    conn.execute("BEGIN")
    conn.execute("INSERT INTO tenants VALUES (?,?)", (TENANT_A, "Demo GBA Trading tenant"))
    conn.execute("INSERT INTO tenants VALUES (?,?)", (TENANT_B, "Demo Other Workshop tenant"))
    for uid, tenant, username, role, name in (
        ("usr_owner_a", TENANT_A, "owner@demo-gba", "owner", "Demo owner (GBA Trading)"),
        ("usr_viewer_a", TENANT_A, "viewer@demo-gba", "viewer", "Demo viewer (GBA Trading)"),
        ("usr_owner_b", TENANT_B, "owner@demo-other", "owner", "Demo owner (Other Workshop)"),
    ):
        conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (uid, tenant, username, pw, role, name))
    conn.execute("INSERT INTO businesses (business_id, tenant_id, name, currency, timezone, opening_cash_minor, opening_date, buffer_minor, horizon_end, "
                 "input_version, order_json, synthetic) VALUES (?,?,?,?,?,?,?,?,?,1,?,1)",
                 (b["business_id"], TENANT_A, b["display_name"], "CNY", b["timezone"], parse_amount_minor(b["opening_cash_cny"]), b["opening_date"],
                  parse_amount_minor(b["owner_buffer_cny"]), b["horizon_end"], json.dumps(b["order"])))
    for c in read_json("counterparties.json"):
        conn.execute("INSERT INTO counterparties VALUES (?,?,?,?,?,?)",
                     (TENANT_A, c["counterparty_id"], c["display_name"], c["role"], c["test_account"], 1 if c["payment_allowlisted"] else 0))
    # Second tenant for isolation tests
    conn.execute("INSERT INTO businesses (business_id, tenant_id, name, currency, timezone, opening_cash_minor, opening_date, buffer_minor, horizon_end, "
                 "input_version, order_json, synthetic) VALUES (?,?,?,?,?,?,?,?,?,1,NULL,1)",
                 ("demo_other_002", TENANT_B, "Demo Other Workshop", "CNY", "Asia/Shanghai", 5_000_000, "2026-10-01", 1_000_000, "2026-11-16"))
    conn.execute("INSERT INTO counterparties VALUES (?,?,?,?,?,?)", (TENANT_B, "SUP-OTHER-900", "Other tenant supplier (synthetic)", "supplier", "SANDBOX-6222000000000900", 1))
    orig = lambda eid: json.dumps({"event_id": eid, "note": "seeded synthetic record for tenant isolation tests"})  # noqa: E731
    for eid, d, direction, amt, cp in (("OTH-001", "2026-10-05", "in", 1_500_000, "CUST-OTH-1"), ("OTH-002", "2026-10-09", "out", 800_000, "SUP-OTHER-900")):
        conn.execute("INSERT INTO cash_events (tenant_id, event_id, business_id, date, direction, amount_minor, currency, category, counterparty_id, source_document_id, "
                     "source_ref, confirmation_status, description, order_id, source_id, original_json, created_in_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                     (TENANT_B, eid, "demo_other_002", d, direction, amt, "CNY", "misc", cp, "SYN-OTHER-DOC", f"seed#{eid}", "synthetic",
                      "Synthetic record owned by the second tenant", None, None, orig(eid)))
    conn.execute("INSERT INTO audit_events (tenant_id, ts, actor_type, actor_id, event_type, detail_json) VALUES (?,?,?,?,?,?)",
                 (TENANT_A, utcnow_iso(), "system", None, "workspace_seeded", json.dumps({"label": "synthetic demo workspace"})))
    conn.execute("COMMIT")
    conn.close()
    if load_example:
        from .db import reset_thread_connections
        from .services.auth import login
        from .services.workspace import load_example as _load
        old = config.DB_PATH
        config.DB_PATH = path
        reset_thread_connections()
        try:
            _, _, actor = login("owner@demo-gba", demo_password())
            _load(actor)
        finally:
            config.DB_PATH = old
            reset_thread_connections()
    return path
