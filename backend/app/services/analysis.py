"""Stored forecast runs, comparisons, conditions, financing and the deterministic decision envelope."""
from __future__ import annotations

import json
import secrets
from datetime import date

from ..db import audit, get_conn, utcnow_iso, write_tx
from ..domain.engine import EngineError, assess_financing, run_scenario
from ..fixtures_loader import catalogue, scenario_defs
from .errors import Actor, AppError, require_owner
from .workspace import active_account, condition_status, load_inputs

SCENARIO_IDS = [s["scenario_id"] for s in scenario_defs()["scenarios"]]
DEBT_FREE_PLANS = ["buyer_deposit", "supplier_deferral", "combined_terms"]


def _engine(fn, *a, **k):
    try:
        return fn(*a, **k)
    except EngineError as exc:
        raise AppError(exc.code, str(exc)) from exc


def run_forecast(actor: Actor, scenario_id: str, horizon_end: str | None = None, extend_horizon: bool = True) -> dict:
    """Compute and store a run. Read-only with respect to ledger and sandbox cash."""
    if scenario_id not in SCENARIO_IDS:
        raise AppError("VALIDATION_ERROR", f"Unknown scenario '{scenario_id}'.", field_errors={"scenario_id": f"one of {SCENARIO_IDS}"})
    conn = get_conn()
    inputs = load_inputs(actor.tenant_id, conn)
    if not inputs.events:
        raise AppError("MISSING_EVIDENCE", "No cash records yet. Load the synthetic example or import a CSV first.")
    he = None
    if horizon_end:
        try:
            he = date.fromisoformat(horizon_end)
        except ValueError as exc:
            raise AppError("VALIDATION_ERROR", "horizon_end must be YYYY-MM-DD") from exc
    result = _engine(run_scenario, inputs, scenario_id, scenario_defs(), catalogue(), condition_status(actor.tenant_id, conn),
                     horizon_end=he, extend_horizon=extend_horizon)
    acct = active_account(actor.tenant_id, conn)
    run_id = "run_" + secrets.token_hex(6)
    result["run_id"] = run_id
    result["account_version"] = acct["ledger_version"] if acct else None
    result["created_at"] = utcnow_iso()
    with write_tx(conn):
        conn.execute("INSERT INTO forecast_runs (run_id, tenant_id, scenario_id, input_version, account_version, result_json, created_at) VALUES (?,?,?,?,?,?,?)",
                     (run_id, actor.tenant_id, scenario_id, inputs.input_version, result["account_version"], json.dumps(result), result["created_at"]))
    return result


def get_run(actor: Actor, run_id: str) -> dict:
    r = get_conn().execute("SELECT result_json FROM forecast_runs WHERE tenant_id = ? AND run_id = ?", (actor.tenant_id, run_id)).fetchone()
    if not r:
        raise AppError("NOT_FOUND", "Run not found.", 404)
    return json.loads(r["result_json"])


def compare(actor: Actor, scenario_ids: list[str] | None = None, expected_input_version: int | None = None) -> dict:
    ids = scenario_ids or SCENARIO_IDS
    inputs_version = load_inputs(actor.tenant_id).input_version
    if expected_input_version is not None and expected_input_version != inputs_version:
        raise AppError("VERSION_CONFLICT", f"Inputs are now at version {inputs_version}.", 409)
    runs = [run_forecast(actor, sid) for sid in ids]
    rows = []
    for r in runs:
        m, e = r["metrics"], r["economics"]
        rows.append({
            "scenario_id": r["scenario_id"], "label": r["label"], "run_id": r["run_id"], "terms_status": r["terms_status"],
            "complete": r["complete"], "lowest_balance_minor": m["lowest_balance_minor"], "lowest_balance_date": m["lowest_balance_date"],
            "first_negative_date": m["first_negative_date"], "required_support_minor": m["required_support_minor"],
            "ending_balance_minor": m["ending_balance_minor"], "borrowed_principal_minor": e["borrowed_principal_minor"],
            "financing_cost_minor": e["financing_cost_minor"], "repayment_date": (r["financing"] or {}).get("repayment_date"),
            "contribution_before_financing_minor": e["contribution_before_financing_minor"],
            "contribution_after_financing_minor": e["contribution_after_financing_minor"],
            "meets_buffer": r["complete"] and m["lowest_balance_minor"] >= m["buffer_minor"],
            "conditions": r["conditions"], "unresolved_conditions": r["unresolved_conditions"],
        })
    return {"input_version": inputs_version, "scenarios": rows, "runs": {r["run_id"]: r for r in runs}}


def set_condition(actor: Actor, condition_id: str, accept: bool) -> dict:
    """Owner records synthetic counterparty acceptance. Selecting a plan never does this."""
    require_owner(actor)
    cdefs = scenario_defs()["conditions"]
    if condition_id not in cdefs:
        raise AppError("VALIDATION_ERROR", "Unknown condition.")
    if not cdefs[condition_id]["acceptable_by_owner"]:
        raise AppError("POLICY_BLOCKED", "Credit eligibility cannot be marked accepted; real borrowing is out of scope and remains not assessed.", 403)
    status = "accepted" if accept else "proposed"
    conn = get_conn()
    from .workspace import bump_input_version
    with write_tx(conn):
        conn.execute("INSERT INTO scenario_conditions (tenant_id, condition_id, status, confirmed_by, confirmed_at, note) VALUES (?,?,?,?,?,?) "
                     "ON CONFLICT(tenant_id, condition_id) DO UPDATE SET status=excluded.status, confirmed_by=excluded.confirmed_by, "
                     "confirmed_at=excluded.confirmed_at, note=excluded.note",
                     (actor.tenant_id, condition_id, status, actor.username, utcnow_iso(), "Mark accepted in this synthetic case"))
        bump_input_version(conn, actor, f"condition {condition_id} -> {status}")
        audit(conn, actor.tenant_id, "user", actor.user_id, "condition_recorded", decision_code=status,
              detail={"condition_id": condition_id, "status": status, "label": cdefs[condition_id]["label"]})
    return conditions(actor)


def conditions(actor: Actor) -> list[dict]:
    rows = {r["condition_id"]: dict(r) for r in get_conn().execute("SELECT * FROM scenario_conditions WHERE tenant_id = ?", (actor.tenant_id,))}
    out = []
    for cid, c in scenario_defs()["conditions"].items():
        r = rows.get(cid, {})
        out.append({"condition_id": cid, "label": c["label"], "acceptable_by_owner": c["acceptable_by_owner"],
                    "status": c.get("fixed_status") or r.get("status", "proposed"), "confirmed_by": r.get("confirmed_by"), "confirmed_at": r.get("confirmed_at")})
    return out


def financing_options(actor: Actor, purpose: str = "working_capital") -> list[dict]:
    if purpose not in ("working_capital", "equipment_acquisition"):
        raise AppError("VALIDATION_ERROR", "purpose must be working_capital or equipment_acquisition")
    inputs = load_inputs(actor.tenant_id)
    return _engine(assess_financing, inputs, scenario_defs(), catalogue(), condition_status(actor.tenant_id), purpose)


def decision(actor: Actor, comparison: dict | None = None) -> dict:
    """Deterministic decision envelope built only from stored financial results."""
    comp = comparison or compare(actor)
    rows = {r["scenario_id"]: r for r in comp["scenarios"]}
    cur = rows["current_terms"]
    fact = lambda sid, key: {"run_id": rows[sid]["run_id"], "metric_key": key}  # noqa: E731
    acct = active_account(actor.tenant_id)
    base = {"execution_mode": None, "fact_refs": [], "evidence_refs": [], "assumptions": [], "unresolved_conditions": [], "proposed_actions": []}
    run = comp["runs"][cur["run_id"]]
    base["assumptions"] = run["assumptions"]
    base["evidence_refs"] = sorted({e["event_id"] for e in run["ledger"] if e["origin"] == "record"})
    if not cur["complete"]:
        base.update(decision_code="needs_information", summary="Some critical inputs are missing, so a complete cash decision is not possible. "
                    "Fix the flagged records in Evidence; no action can be authorised from a partial forecast.",
                    fact_refs=[], unresolved_conditions=[{"issue": i} for i in run["issues"]])
        return base
    base["fact_refs"] = [fact("current_terms", k) for k in ("first_negative_date", "lowest_balance_minor", "lowest_balance_date", "required_support_minor")]
    if cur["meets_buffer"]:
        base.update(decision_code="ready_for_simulation", summary="On current terms the order keeps cash at or above your buffer throughout the horizon.")
        return base
    passing = [rows[s] for s in DEBT_FREE_PLANS if s in rows and rows[s]["meets_buffer"]]
    accepted = [p for p in passing if p["terms_status"] == "accepted"]
    if accepted:
        p = accepted[0]
        base["fact_refs"] += [fact(p["scenario_id"], "lowest_balance_minor")]
        actions = []
        if acct is None:
            actions.append({"type": "initialize_sandbox", "scenario_id": p["scenario_id"]})
        else:
            actions.append({"type": "prepare_sandbox_payment", "scenario_id": p["scenario_id"], "obligation_event_id": "ORD-001-MAT-1",
                            "recipient_id": "SUP-MAT-001", "amount_minor": 7_000_000})
        base.update(decision_code="ready_for_simulation", proposed_actions=actions,
                    summary=f"With the accepted terms in '{p['label']}', projected cash stays at or above your buffer. "
                            "You can prepare the first synthetic supplier payment for your explicit approval.")
        return base
    if passing:
        p = passing[0]
        base["fact_refs"] += [fact(p["scenario_id"], "lowest_balance_minor"), fact(p["scenario_id"], "ending_balance_minor")]
        base.update(decision_code="conditional_terms", unresolved_conditions=p["unresolved_conditions"],
                    summary=f"Current terms breach your buffer. '{p['label']}' keeps cash above the buffer without borrowing, "
                            "but only if the counterparties agree. It stays conditional until you record each acceptance.")
        return base
    base.update(decision_code="funding_required", summary="No debt-free plan keeps cash above your buffer. Illustrative financing can be compared, "
                "but credit eligibility is not assessed and borrowing cannot be executed here.")
    return base
