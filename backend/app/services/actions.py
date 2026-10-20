"""Isolated sandbox, immutable prepared actions, exact-hash owner approval and atomic idempotent execution."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from .. import config
from ..db import audit, clock, get_conn, utcnow_iso, write_tx
from ..domain.engine import run_scenario
from ..domain.money import MoneyError, parse_amount_minor
from ..fixtures_loader import catalogue, read_json, scenario_defs
from .errors import Actor, AppError, not_found, require_owner
from .workspace import active_account, condition_status, load_inputs

ALLOWED_ACTION_TYPES = {"sandbox_supplier_payment"}
RED_OPERATIONS = {"real_payment", "real_borrowing", "fx_trade", "loan_drawdown", "add_recipient", "change_limit"}
TERMINAL = {"succeeded", "blocked", "expired", "cancelled", "failed"}


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def mask(account: str | None) -> str | None:
    if not account:
        return None
    return account[:8] + "*" * max(0, len(account) - 12) + account[-4:]


# ---------------------------------------------------------------- sandbox

def initialize_sandbox(actor: Actor) -> dict:
    """Synthetic seeding of the isolated day-3 sandbox for the accepted combined-terms case. Not an LLM tool."""
    require_owner(actor)
    boot = read_json("sandbox_bootstrap.json")
    conn = get_conn()
    with write_tx(conn):
        existing = active_account(actor.tenant_id, conn)
        if existing:
            return sandbox_view(actor, conn)
        status = condition_status(actor.tenant_id, conn)
        missing = [c for c in boot["required_conditions"] if status.get(c) != "accepted"]
        if missing:
            raise AppError("POLICY_BLOCKED", f"Record acceptance of {', '.join(missing)} before initializing the {boot['scenario_id']} sandbox.", 409)
        events = {r["event_id"] for r in conn.execute("SELECT event_id FROM cash_events WHERE tenant_id = ?", (actor.tenant_id,))}
        needed = {s["event_id"] for s in boot["settled_inputs"] if not s["event_id"].startswith("ORD-001-DEP")}
        if not needed <= events:
            raise AppError("MISSING_EVIDENCE", "Load the synthetic example before initializing the sandbox.", 409)
        account_id = "sbx_" + secrets.token_hex(5)
        bal = parse_amount_minor(boot["opening_cash_cny"])
        now = utcnow_iso()
        conn.execute("INSERT INTO sandbox_accounts (account_id, tenant_id, currency, available_minor, simulated_date, ledger_version, scenario_id, active, created_at) "
                     "VALUES (?,?,?,?,?,?,?,1,?)", (account_id, actor.tenant_id, "CNY", bal, boot["simulated_date"], 1, boot["scenario_id"], now))
        conn.execute("INSERT INTO sandbox_ledger (account_id, tenant_id, simulated_date, delta_minor, balance_after_minor, reason, ts) VALUES (?,?,?,?,?,?,?)",
                     (account_id, actor.tenant_id, "2026-10-01", bal, bal, "synthetic_seed_opening_cash", now))
        for s in boot["settled_inputs"]:
            amt = parse_amount_minor(s["amount_cny"])
            delta = amt if s["direction"] == "in" else -amt
            bal += delta
            conn.execute("INSERT INTO sandbox_ledger (account_id, tenant_id, simulated_date, delta_minor, balance_after_minor, reason, event_id, ts) "
                         "VALUES (?,?,?,?,?,?,?,?)", (account_id, actor.tenant_id, s["actual_date"], delta, bal, "synthetic_seed_settled_input", s["event_id"], now))
            conn.execute("INSERT INTO settlements (settlement_id, tenant_id, account_id, event_id, actual_date, amount_minor, kind, created_at) VALUES (?,?,?,?,?,?,?,?)",
                         ("stl_" + secrets.token_hex(6), actor.tenant_id, account_id, s["event_id"], s["actual_date"], amt, "synthetic_seed", now))
        if bal != parse_amount_minor(boot["expected_available_cny"]):
            raise AppError("FAILED", "Sandbox bootstrap did not reconcile to the documented available cash.", 500)
        conn.execute("UPDATE sandbox_accounts SET available_minor = ? WHERE account_id = ?", (bal, account_id))
        audit(conn, actor.tenant_id, "user", actor.user_id, "sandbox_initialized", detail={"account_id": account_id, "available_minor": bal,
              "label": "Synthetic seeding, not a deposit from a real bank"})
        return sandbox_view(actor, conn)


def sandbox_view(actor: Actor, conn=None) -> dict | None:
    conn = conn or get_conn()
    a = active_account(actor.tenant_id, conn)
    if not a:
        return None
    ledger = [dict(r) for r in conn.execute("SELECT simulated_date, delta_minor, balance_after_minor, reason, event_id, action_id, ts FROM sandbox_ledger "
                                            "WHERE tenant_id = ? AND account_id = ? ORDER BY entry_id", (actor.tenant_id, a["account_id"]))]
    return {"account_id": a["account_id"], "currency": a["currency"], "available_minor": a["available_minor"], "simulated_date": a["simulated_date"],
            "ledger_version": a["ledger_version"], "scenario_id": a["scenario_id"], "ledger": ledger, "synthetic": True}


# ---------------------------------------------------------------- policy

def _policy_checks(conn, tenant_id: str, payload: dict, acct, *, at_execution: bool) -> list[dict]:
    p = config.POLICY
    checks: list[dict] = []

    def add(check, passed, detail, code="POLICY_BLOCKED"):
        checks.append({"check": check, "passed": bool(passed), "detail": detail, "code": None if passed else code})

    add("action_type_allowed", payload["action_type"] in ALLOWED_ACTION_TYPES, f"{payload['action_type']} is a yellow sandbox operation")
    add("currency", payload["currency"] == p["currency"], "CNY only; no FX")
    rec = conn.execute("SELECT * FROM counterparties WHERE tenant_id = ? AND counterparty_id = ?", (tenant_id, payload["recipient_id"])).fetchone()
    add("recipient_allowlisted", rec is not None and rec["payment_allowlisted"] == 1,
        "seeded allowlisted recipient" if rec and rec["payment_allowlisted"] else "recipient is not on this tenant's allowlist", "RECIPIENT_NOT_ALLOWED")
    add("per_payment_limit", payload["amount_minor"] <= p["per_payment_limit_minor"],
        f"{payload['amount_minor']/100:.2f} vs limit {p['per_payment_limit_minor']/100:.2f}")
    used = 0
    if acct:
        used = -(conn.execute("SELECT COALESCE(SUM(delta_minor),0) FROM sandbox_ledger WHERE account_id = ? AND simulated_date = ? AND reason = 'sandbox_payment'",
                              (acct["account_id"], acct["simulated_date"])).fetchone()[0])
    add("daily_outgoing_limit", used + payload["amount_minor"] <= p["daily_outgoing_limit_minor"],
        f"used {used/100:.2f} + {payload['amount_minor']/100:.2f} vs limit {p['daily_outgoing_limit_minor']/100:.2f}")
    if acct:
        after = acct["available_minor"] - payload["amount_minor"]
        add("available_cash_and_buffer", after >= p["min_account_buffer_minor"],
            f"available {acct['available_minor']/100:.2f} -> {after/100:.2f}; minimum immediate buffer {p['min_account_buffer_minor']/100:.2f}", "INSUFFICIENT_CASH")
    else:
        add("available_cash_and_buffer", False, "no initialized sandbox account", "INSUFFICIENT_CASH")
    # selected plan: conditions accepted and recalculated cash policy still holds
    status = condition_status(tenant_id, conn)
    inputs = load_inputs(tenant_id, conn)
    plan = run_scenario(inputs, payload["scenario_id"], scenario_defs(), catalogue(), status)
    add("plan_conditions_accepted", plan["terms_status"] == "accepted",
        "all required terms accepted" if plan["terms_status"] == "accepted" else f"terms status is {plan['terms_status']}")
    add("plan_cash_policy", plan["complete"] and plan["metrics"]["lowest_balance_minor"] >= inputs.buffer_minor,
        f"recalculated lowest projected balance {plan['metrics']['lowest_balance_minor']/100:.2f} vs buffer {inputs.buffer_minor/100:.2f}"
        + ("" if plan["complete"] else "; forecast incomplete"), "MISSING_EVIDENCE" if not plan["complete"] else "POLICY_BLOCKED")
    ob = next((e for e in plan["ledger"] if e["event_id"] == payload["obligation_event_id"]), None)
    settled = sum(s.amount_minor for s in inputs.settlements if s.event_id == payload["obligation_event_id"])
    outstanding = (ob["amount_minor"] - settled) if ob and ob["amount_minor"] is not None else 0
    add("obligation_outstanding", ob is not None and payload["amount_minor"] <= outstanding,
        f"obligation {payload['obligation_event_id']} outstanding {outstanding/100:.2f}" if ob else "obligation not in the selected plan")
    add("recipient_matches_obligation", ob is not None and ob["counterparty_id"] == payload["recipient_id"],
        "recipient is the obligation's counterparty" if ob and ob["counterparty_id"] == payload["recipient_id"] else "recipient differs from the obligation's counterparty",
        "RECIPIENT_NOT_ALLOWED")
    return checks


def _first_failure(checks: list[dict]) -> dict | None:
    return next((c for c in checks if not c["passed"]), None)


# ---------------------------------------------------------------- prepare

def prepare_payment(actor: Actor, *, scenario_id: str, obligation_event_id: str, recipient_id: str, amount: str,
                    idempotency_key: str, prepared_by: str = "owner_ui", action_type: str = "sandbox_supplier_payment") -> dict:
    """Create an immutable prepared payload. Grants no approval."""
    require_owner(actor)
    if action_type in RED_OPERATIONS:
        conn = get_conn()
        with write_tx(conn):
            audit(conn, actor.tenant_id, prepared_by, actor.user_id, "action_blocked", decision_code="POLICY_BLOCKED",
                  detail={"action_type": action_type, "reason": "red operation"})
        raise AppError("POLICY_BLOCKED", f"'{action_type}' is a prohibited operation in this prototype.", 403)
    if not idempotency_key or len(idempotency_key) > 100:
        raise AppError("VALIDATION_ERROR", "idempotency_key is required (max 100 chars).")
    try:
        amount_minor = parse_amount_minor(amount)
    except MoneyError as exc:
        raise AppError("VALIDATION_ERROR", str(exc), field_errors={"amount": str(exc)}) from exc
    conn = get_conn()
    with write_tx(conn):
        request_sig = {"action_type": action_type, "scenario_id": scenario_id, "obligation_event_id": obligation_event_id,
                       "recipient_id": recipient_id, "amount_minor": amount_minor}
        prior = conn.execute("SELECT * FROM actions WHERE tenant_id = ? AND idempotency_key = ?", (actor.tenant_id, idempotency_key)).fetchone()
        if prior:
            pp = json.loads(prior["payload_json"])
            if {k: pp[k] for k in request_sig} != request_sig:
                raise AppError("IDEMPOTENCY_CONFLICT", "This idempotency key was already used for a different payment.", 409)
            return action_view(actor, prior["action_id"], conn)
        acct = active_account(actor.tenant_id, conn)
        b = conn.execute("SELECT * FROM businesses WHERE tenant_id = ?", (actor.tenant_id,)).fetchone()
        inputs = load_inputs(actor.tenant_id, conn)
        status = condition_status(actor.tenant_id, conn)
        if scenario_id not in {s["scenario_id"] for s in scenario_defs()["scenarios"]}:
            raise AppError("VALIDATION_ERROR", "Unknown scenario.")
        plan = run_scenario(inputs, scenario_id, scenario_defs(), catalogue(), status)
        run_id = "run_" + secrets.token_hex(6)
        plan["run_id"] = run_id
        conn.execute("INSERT INTO forecast_runs (run_id, tenant_id, scenario_id, input_version, account_version, result_json, created_at) VALUES (?,?,?,?,?,?,?)",
                     (run_id, actor.tenant_id, scenario_id, inputs.input_version, acct["ledger_version"] if acct else None, json.dumps(plan), utcnow_iso()))
        action_id = "act_" + secrets.token_hex(8)
        payload = {
            "action_id": action_id, "tenant_id": actor.tenant_id, "action_type": action_type, "recipient_id": recipient_id,
            "obligation_event_id": obligation_event_id, "amount_minor": amount_minor, "currency": "CNY",
            "simulated_execution_date": acct["simulated_date"] if acct else None, "scenario_id": scenario_id, "financial_run_id": run_id,
            "input_version": b["input_version"], "account_id": acct["account_id"] if acct else None,
            "account_version": acct["ledger_version"] if acct else None, "policy_version": config.POLICY["policy_version"],
        }
        checks = _policy_checks(conn, actor.tenant_id, payload, acct, at_execution=False)
        fail = _first_failure(checks)
        state = "blocked" if fail else "awaiting_approval"
        now = utcnow_iso()
        conn.execute("INSERT INTO actions (action_id, tenant_id, action_type, payload_json, payload_hash, state, idempotency_key, policy_checks_json, "
                     "failure_code, failure_reason, prepared_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (action_id, actor.tenant_id, action_type, canonical(payload), payload_hash(payload), state, idempotency_key, json.dumps(checks),
                      fail["code"] if fail else None, fail["detail"] if fail else None, prepared_by, now, now))
        audit(conn, actor.tenant_id, prepared_by, actor.user_id, "action_prepared", action_id=action_id,
              decision_code=fail["code"] if fail else "AWAITING_APPROVAL", detail={"state": state, "amount_minor": amount_minor, "recipient_id": recipient_id,
                                                                                  "payload_hash": payload_hash(payload)})
        return action_view(actor, action_id, conn)


# ---------------------------------------------------------------- approve

def approve(actor: Actor, action_id: str, shown_payload_hash: str) -> dict:
    """Owner binds approval to the exact payload hash they reviewed. Never a model tool."""
    require_owner(actor)
    conn = get_conn()
    with write_tx(conn):
        a = conn.execute("SELECT * FROM actions WHERE tenant_id = ? AND action_id = ?", (actor.tenant_id, action_id)).fetchone()
        if not a:
            raise not_found("Action")
        if a["state"] != "awaiting_approval":
            raise AppError("APPROVAL_REQUIRED" if a["state"] == "prepared" else "POLICY_BLOCKED",
                           f"Action is {a['state']} and cannot be approved.", 409)
        payload = json.loads(a["payload_json"])
        if payload_hash(payload) != a["payload_hash"] or shown_payload_hash != a["payload_hash"]:
            raise AppError("VERSION_CONFLICT", "The reviewed payload does not match the prepared action. Reload the preview.", 409)
        stale = _version_problems(conn, actor.tenant_id, payload)
        if stale:
            raise AppError("VERSION_CONFLICT", stale, 409)
        now = clock.now()
        approval_id = "apv_" + secrets.token_hex(6)
        conn.execute("INSERT INTO approvals (approval_id, tenant_id, action_id, actor_user_id, payload_hash, policy_version, approved_at, expires_at, state, "
                     "execution_capability_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (approval_id, actor.tenant_id, action_id, actor.user_id, a["payload_hash"], payload["policy_version"], now.isoformat(),
                      (now + timedelta(seconds=config.POLICY["approval_ttl_seconds"])).isoformat(), "active",
                      hashlib.sha256(f"{approval_id}:{a['payload_hash']}".encode()).hexdigest()))
        conn.execute("UPDATE actions SET state='approved', updated_at=? WHERE action_id=?", (now.isoformat(), action_id))
        audit(conn, actor.tenant_id, "user", actor.user_id, "action_approved", action_id=action_id, decision_code="APPROVED",
              detail={"approval_id": approval_id, "payload_hash": a["payload_hash"]})
        return action_view(actor, action_id, conn)


def _version_problems(conn, tenant_id: str, payload: dict) -> str | None:
    b = conn.execute("SELECT input_version FROM businesses WHERE tenant_id = ?", (tenant_id,)).fetchone()
    acct = active_account(tenant_id, conn)
    if b["input_version"] != payload["input_version"]:
        return f"Evidence/input version changed ({payload['input_version']} -> {b['input_version']}); re-prepare and re-approve."
    if not acct or acct["account_id"] != payload["account_id"] or acct["ledger_version"] != payload["account_version"]:
        return "Sandbox account version changed; re-prepare and re-approve."
    if payload["policy_version"] != config.POLICY["policy_version"]:
        return "Policy version changed; re-prepare and re-approve."
    return None


# ---------------------------------------------------------------- execute

def execute(actor: Actor, action_id: str, *, idempotency_key: str | None = None, via: str = "owner_ui",
            agent_scope_action_id: str | None = None) -> dict:
    """Revalidate everything server-side and commit the simulated payment exactly once."""
    require_owner(actor)
    if via == "agent" and agent_scope_action_id != action_id:
        raise AppError("POLICY_BLOCKED", "This agent run is only scoped to execute the owner-approved action it was resumed for.", 403)
    conn = get_conn()
    error: AppError | None = None
    with write_tx(conn):
        a = conn.execute("SELECT * FROM actions WHERE tenant_id = ? AND action_id = ?", (actor.tenant_id, action_id)).fetchone()
        if not a:
            raise not_found("Action")
        if idempotency_key is not None and idempotency_key != a["idempotency_key"]:
            raise AppError("IDEMPOTENCY_CONFLICT", "Idempotency key does not match this action.", 409)
        if a["state"] == "succeeded":
            audit(conn, actor.tenant_id, via, actor.user_id, "execute_replayed", action_id=action_id, decision_code="ALREADY_SUCCEEDED")
            return action_view(actor, action_id, conn)
        if a["state"] != "approved":
            code = {"awaiting_approval": "APPROVAL_REQUIRED", "prepared": "APPROVAL_REQUIRED", "expired": "APPROVAL_EXPIRED"}.get(a["state"], a["failure_code"] or "POLICY_BLOCKED")
            audit(conn, actor.tenant_id, via, actor.user_id, "execute_rejected", action_id=action_id, decision_code=code, detail={"state": a["state"]})
            error = AppError(code, f"Action is {a['state']}; it cannot be executed." + (f" {a['failure_reason']}" if a["failure_reason"] else ""), 409)
        else:
            error = _execute_locked(conn, actor, a, via)
    if error:
        raise error
    return action_view(actor, action_id)


def _block(conn, actor, a, via, code, reason, state="blocked") -> AppError:
    conn.execute("UPDATE actions SET state=?, failure_code=?, failure_reason=?, updated_at=? WHERE action_id=?",
                 (state, code, reason, utcnow_iso(), a["action_id"]))
    conn.execute("UPDATE approvals SET state=? WHERE action_id=? AND state='active'", ("expired" if state == "expired" else "invalidated", a["action_id"]))
    audit(conn, actor.tenant_id, via, actor.user_id, "execute_rejected", action_id=a["action_id"], decision_code=code, detail={"reason": reason})
    return AppError(code, reason, 409)


def _execute_locked(conn, actor: Actor, a, via: str) -> AppError | None:
    apv = conn.execute("SELECT * FROM approvals WHERE tenant_id = ? AND action_id = ? AND state = 'active' ORDER BY approved_at DESC LIMIT 1",
                       (actor.tenant_id, a["action_id"])).fetchone()
    if not apv:
        return _block(conn, actor, a, via, "APPROVAL_REQUIRED", "No active owner approval exists for this action.")
    if datetime.fromisoformat(apv["expires_at"]) <= clock.now():
        return _block(conn, actor, a, via, "APPROVAL_EXPIRED", "The owner approval expired; prepare and approve again.", state="expired")
    payload = json.loads(a["payload_json"])
    h = payload_hash(payload)
    if h != a["payload_hash"] or h != apv["payload_hash"] or apv["policy_version"] != config.POLICY["policy_version"]:
        return _block(conn, actor, a, via, "VERSION_CONFLICT", "Payload or policy differs from what the owner approved; approval is stale.")
    stale = _version_problems(conn, actor.tenant_id, payload)
    if stale:
        return _block(conn, actor, a, via, "VERSION_CONFLICT", stale)
    acct = active_account(actor.tenant_id, conn)
    checks = _policy_checks(conn, actor.tenant_id, payload, acct, at_execution=True)
    fail = _first_failure(checks)
    if fail:
        conn.execute("UPDATE actions SET policy_checks_json=? WHERE action_id=?", (json.dumps(checks), a["action_id"]))
        return _block(conn, actor, a, via, fail["code"], f"Policy check '{fail['check']}' failed at execution: {fail['detail']}")
    # ---- atomic economic effect (same transaction) ----
    now = utcnow_iso()
    conn.execute("UPDATE actions SET state='executing', updated_at=? WHERE action_id=?", (now, a["action_id"]))
    before = acct["available_minor"]
    after = before - payload["amount_minor"]
    conn.execute("UPDATE sandbox_accounts SET available_minor=?, ledger_version=ledger_version+1 WHERE account_id=? AND ledger_version=?",
                 (after, acct["account_id"], acct["ledger_version"]))
    conn.execute("INSERT INTO sandbox_ledger (account_id, tenant_id, simulated_date, delta_minor, balance_after_minor, reason, event_id, action_id, ts) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (acct["account_id"], actor.tenant_id, payload["simulated_execution_date"], -payload["amount_minor"], after,
                                               "sandbox_payment", payload["obligation_event_id"], a["action_id"], now))
    settlement_id = "stl_" + secrets.token_hex(6)
    conn.execute("INSERT INTO settlements (settlement_id, tenant_id, account_id, event_id, actual_date, amount_minor, action_id, kind, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (settlement_id, actor.tenant_id, acct["account_id"], payload["obligation_event_id"],
                                               payload["simulated_execution_date"], payload["amount_minor"], a["action_id"], "sandbox_payment", now))
    rec = conn.execute("SELECT * FROM counterparties WHERE tenant_id=? AND counterparty_id=?", (actor.tenant_id, payload["recipient_id"])).fetchone()
    receipt = {
        "receipt_id": "rcpt_" + secrets.token_hex(6), "action_id": a["action_id"], "status": "Simulated payment settled in sandbox",
        "simulated": True, "settled_amount_minor": payload["amount_minor"], "currency": "CNY", "recipient_id": payload["recipient_id"],
        "recipient_name": rec["display_name"], "recipient_account_masked": mask(rec["test_account"]),
        "balance_before_minor": before, "balance_after_minor": after, "simulated_date": payload["simulated_execution_date"],
        "settlement_id": settlement_id, "obligation_event_id": payload["obligation_event_id"], "financial_run_id": payload["financial_run_id"],
        "input_version": payload["input_version"], "account_version_before": payload["account_version"], "account_version_after": payload["account_version"] + 1,
        "policy_version": payload["policy_version"], "approval_id": apv["approval_id"], "approved_by": apv["actor_user_id"],
        "approved_at": apv["approved_at"], "approval_expires_at": apv["expires_at"], "payload_hash": a["payload_hash"],
        "executed_at": now, "executed_via": via,
        "note": "Sandbox simulation only. No real money moved; internal hashes do not prove real-world transaction truth.",
    }
    conn.execute("UPDATE actions SET state='succeeded', receipt_json=?, policy_checks_json=?, updated_at=? WHERE action_id=?",
                 (json.dumps(receipt), json.dumps(checks), now, a["action_id"]))
    conn.execute("UPDATE approvals SET state='consumed' WHERE approval_id=?", (apv["approval_id"],))
    audit(conn, actor.tenant_id, via, actor.user_id, "action_executed", action_id=a["action_id"], decision_code="SUCCEEDED",
          tool_name="execute_approved_sandbox_action" if via == "agent" else None,
          detail={"settlement_id": settlement_id, "before": before, "after": after, "receipt_id": receipt["receipt_id"]})
    return None


def cancel(actor: Actor, action_id: str) -> dict:
    require_owner(actor)
    conn = get_conn()
    with write_tx(conn):
        a = conn.execute("SELECT * FROM actions WHERE tenant_id = ? AND action_id = ?", (actor.tenant_id, action_id)).fetchone()
        if not a:
            raise not_found("Action")
        if a["state"] in TERMINAL:
            raise AppError("VALIDATION_ERROR", f"Action is already {a['state']}.", 409)
        conn.execute("UPDATE actions SET state='cancelled', failure_code='CANCELLED', failure_reason='Cancelled by owner', updated_at=? WHERE action_id=?",
                     (utcnow_iso(), action_id))
        conn.execute("UPDATE approvals SET state='invalidated' WHERE action_id=? AND state='active'", (action_id,))
        audit(conn, actor.tenant_id, "user", actor.user_id, "action_cancelled", action_id=action_id)
    return action_view(actor, action_id)


def action_view(actor: Actor, action_id: str, conn=None) -> dict:
    conn = conn or get_conn()
    a = conn.execute("SELECT * FROM actions WHERE tenant_id = ? AND action_id = ?", (actor.tenant_id, action_id)).fetchone()
    if not a:
        raise not_found("Action")
    payload = json.loads(a["payload_json"])
    rec = conn.execute("SELECT * FROM counterparties WHERE tenant_id = ? AND counterparty_id = ?", (actor.tenant_id, payload["recipient_id"])).fetchone()
    acct = conn.execute("SELECT * FROM sandbox_accounts WHERE account_id = ? AND tenant_id = ?", (payload["account_id"], actor.tenant_id)).fetchone() if payload["account_id"] else None
    apv = conn.execute("SELECT approval_id, actor_user_id, approved_at, expires_at, state, payload_hash FROM approvals WHERE tenant_id=? AND action_id=? "
                       "ORDER BY approved_at DESC LIMIT 1", (actor.tenant_id, action_id)).fetchone()
    receipt = json.loads(a["receipt_json"]) if a["receipt_json"] else None
    before = receipt["balance_before_minor"] if receipt else (acct["available_minor"] if acct else None)
    ob = conn.execute("SELECT source_document_id, source_ref FROM cash_events WHERE tenant_id=? AND event_id=?", (actor.tenant_id, payload["obligation_event_id"])).fetchone()
    return {
        "action_id": a["action_id"], "state": a["state"], "action_type": a["action_type"], "payload": payload, "payload_hash": a["payload_hash"],
        "idempotency_key": a["idempotency_key"], "policy_checks": json.loads(a["policy_checks_json"]), "failure_code": a["failure_code"],
        "failure_reason": a["failure_reason"], "prepared_by": a["prepared_by"], "created_at": a["created_at"], "updated_at": a["updated_at"],
        "recipient": {"recipient_id": payload["recipient_id"], "display_name": rec["display_name"] if rec else "Unknown recipient",
                      "test_account_masked": mask(rec["test_account"]) if rec else None, "allowlisted": bool(rec and rec["payment_allowlisted"])},
        "balance_before_minor": before, "balance_after_minor": receipt["balance_after_minor"] if receipt else (before - payload["amount_minor"] if before is not None else None),
        "approval": dict(apv) if apv else None, "receipt": receipt,
        "obligation_source": {"event_id": payload["obligation_event_id"], **(dict(ob) if ob else {"note": "scenario term from scenarios.json (replaces ORD-001-MAT)"})},
        "simulated": True,
    }


def list_actions(actor: Actor) -> list[dict]:
    rows = get_conn().execute("SELECT action_id FROM actions WHERE tenant_id = ? ORDER BY created_at DESC", (actor.tenant_id,)).fetchall()
    return [action_view(actor, r["action_id"]) for r in rows]
