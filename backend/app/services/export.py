"""Tenant-scoped audit log and evidence bundle (JSON + CSV in a ZIP). No secrets."""
from __future__ import annotations

import csv
import io
import json
import zipfile

from .. import config
from ..db import get_conn, utcnow_iso
from ..domain.csv_import import escape_csv_text
from .analysis import conditions
from .errors import Actor
from .workspace import business, evidence_list


def audit_log(actor: Actor, limit: int = 500) -> list[dict]:
    rows = get_conn().execute("SELECT audit_id, ts, actor_type, actor_id, event_type, action_id, tool_name, decision_code, detail_json FROM audit_events "
                              "WHERE tenant_id = ? ORDER BY audit_id DESC LIMIT ?", (actor.tenant_id, limit)).fetchall()
    return [{**{k: r[k] for k in r.keys() if k != "detail_json"}, "detail": json.loads(r["detail_json"])} for r in rows]


def evidence_bundle(actor: Actor) -> dict:
    conn = get_conn()
    t = actor.tenant_id
    b = business(actor)
    runs = [{"run_id": r["run_id"], "scenario_id": r["scenario_id"], "input_version": r["input_version"], "account_version": r["account_version"],
             "created_at": r["created_at"], "metrics": json.loads(r["result_json"])["metrics"], "assumptions": json.loads(r["result_json"])["assumptions"],
             "terms_status": json.loads(r["result_json"])["terms_status"]}
            for r in conn.execute("SELECT * FROM forecast_runs WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 200", (t,))]
    actions = [{"action_id": r["action_id"], "state": r["state"], "payload": json.loads(r["payload_json"]), "payload_hash": r["payload_hash"],
                "policy_checks": json.loads(r["policy_checks_json"]), "failure_code": r["failure_code"], "failure_reason": r["failure_reason"],
                "receipt": json.loads(r["receipt_json"]) if r["receipt_json"] else None, "created_at": r["created_at"]}
               for r in conn.execute("SELECT * FROM actions WHERE tenant_id = ? ORDER BY created_at", (t,))]
    approvals = [dict(r) for r in conn.execute("SELECT approval_id, action_id, actor_user_id, payload_hash, policy_version, approved_at, expires_at, state "
                                               "FROM approvals WHERE tenant_id = ? ORDER BY approved_at", (t,))]
    settlements = [dict(r) for r in conn.execute("SELECT settlement_id, account_id, event_id, actual_date, amount_minor, action_id, kind FROM settlements WHERE tenant_id = ?", (t,))]
    ledger = [dict(r) for r in conn.execute("SELECT account_id, simulated_date, delta_minor, balance_after_minor, reason, event_id, action_id, ts FROM sandbox_ledger WHERE tenant_id = ? ORDER BY entry_id", (t,))]
    edits = [dict(r) for r in conn.execute("SELECT event_id, field, old_value, new_value, actor, ts, input_version FROM record_edits WHERE tenant_id = ? ORDER BY edit_id", (t,))]
    agent_runs = [{"agent_run_id": r["agent_run_id"], "mode": r["mode"], "task": r["task"], "status": r["status"], "created_at": r["created_at"],
                   "tool_log": json.loads(r["transcript_json"]).get("tool_log", []), "envelope": json.loads(r["envelope_json"]) if r["envelope_json"] else None}
                  for r in conn.execute("SELECT * FROM agent_runs WHERE tenant_id = ? ORDER BY created_at", (t,))]
    return {
        "export_generated_at": utcnow_iso(), "label": "OrderBridge synthetic demo evidence export",
        "business": {"business_id": b["business_id"], "name": b["name"], "currency": b["currency"], "timezone": b["timezone"], "opening_date": b["opening_date"],
                     "opening_cash_minor": b["opening_cash_minor"], "buffer_minor": b["buffer_minor"], "input_version": b["input_version"], "synthetic": True},
        "policy": config.POLICY, "conditions": conditions(actor), "evidence": evidence_list(actor), "record_edits": edits,
        "forecast_runs": runs, "actions": actions, "approvals": approvals, "settlements": settlements, "sandbox_ledger": ledger,
        "agent_runs": agent_runs, "audit": audit_log(actor, 2000),
        "limitations": ["Synthetic data only.", "Sandbox simulation; no real payment, credit or FX.",
                        "Internal hashes show internal consistency, not real-world transaction truth."],
    }


def events_csv(actor: Actor) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["event_id", "date", "direction", "amount_cny", "currency", "category", "counterparty_id", "source_document_id", "source_ref",
                "confirmation_status", "description", "settled_cny"])
    for r in evidence_list(actor)["records"]:
        w.writerow([escape_csv_text(r["event_id"]), r["date"] or "", r["direction"],
                    "" if r["amount_minor"] is None else f"{r['amount_minor'] / 100:.2f}", r["currency"], escape_csv_text(r["category"]),
                    escape_csv_text(r["counterparty_id"]), escape_csv_text(r["source_document_id"]), escape_csv_text(r["source_ref"]),
                    r["confirmation_status"], escape_csv_text(r["description"]), f"{r['settled_minor'] / 100:.2f}"])
    return buf.getvalue()


def audit_csv(actor: Actor) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["audit_id", "ts", "actor_type", "actor_id", "event_type", "action_id", "tool_name", "decision_code", "detail"])
    for a in audit_log(actor, 5000):
        w.writerow([a["audit_id"], a["ts"], a["actor_type"], a["actor_id"], a["event_type"], a["action_id"], a["tool_name"], a["decision_code"],
                    escape_csv_text(json.dumps(a["detail"], sort_keys=True))])
    return buf.getvalue()


def evidence_zip(actor: Actor) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("evidence.json", json.dumps(evidence_bundle(actor), indent=2))
        z.writestr("cash_events.csv", events_csv(actor))
        z.writestr("audit.csv", audit_csv(actor))
        z.writestr("README.txt", "Synthetic OrderBridge demo export. Amounts are integer minor units (CNY 1 = 100) in JSON, decimal CNY in CSV.\n")
    return buf.getvalue()
