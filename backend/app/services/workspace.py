"""Tenant-scoped business inputs, versions, evidence, imports and corrections."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import date

from ..config import FIXTURES_DIR
from ..db import audit, get_conn, utcnow_iso, write_tx
from ..domain.csv_import import COLUMNS, ImportRejected, compare_with_existing, normalize_row, parse_csv
from ..domain.engine import BusinessInputs, LedgerEvent, Settlement
from ..fixtures_loader import read_json
from .errors import Actor, AppError, not_found, require_owner

EDITABLE_FIELDS = {"date", "direction", "amount_cny", "counterparty_id", "category", "confirmation_status", "description"}


def business(actor: Actor):
    row = get_conn().execute("SELECT * FROM businesses WHERE tenant_id = ?", (actor.tenant_id,)).fetchone()
    if not row:
        raise not_found("Business")
    return row


def active_account(tenant_id: str, conn=None):
    conn = conn or get_conn()
    return conn.execute("SELECT * FROM sandbox_accounts WHERE tenant_id = ? AND active = 1", (tenant_id,)).fetchone()


def condition_status(tenant_id: str, conn=None) -> dict[str, str]:
    conn = conn or get_conn()
    return {r["condition_id"]: r["status"] for r in conn.execute(
        "SELECT condition_id, status FROM scenario_conditions WHERE tenant_id = ?", (tenant_id,))}


def _row_to_event(r) -> LedgerEvent:
    return LedgerEvent(
        event_id=r["event_id"], date=date.fromisoformat(r["date"]) if r["date"] else None, direction=r["direction"],
        amount_minor=r["amount_minor"], currency=r["currency"], category=r["category"] or "", counterparty_id=r["counterparty_id"],
        source_document_id=r["source_document_id"], source_ref=r["source_ref"], confirmation_status=r["confirmation_status"],
        order_id=r["order_id"],
    )


def load_inputs(tenant_id: str, conn=None) -> BusinessInputs:
    conn = conn or get_conn()
    b = conn.execute("SELECT * FROM businesses WHERE tenant_id = ?", (tenant_id,)).fetchone()
    events = [_row_to_event(r) for r in conn.execute("SELECT * FROM cash_events WHERE tenant_id = ? ORDER BY date, event_id", (tenant_id,))]
    acct = active_account(tenant_id, conn)
    settlements = []
    if acct:
        settlements = [Settlement(s["settlement_id"], s["event_id"], date.fromisoformat(s["actual_date"]), s["amount_minor"], s["action_id"])
                       for s in conn.execute("SELECT * FROM settlements WHERE tenant_id = ? AND account_id = ?", (tenant_id, acct["account_id"]))]
    return BusinessInputs(
        business_id=b["business_id"], opening_date=date.fromisoformat(b["opening_date"]), opening_cash_minor=b["opening_cash_minor"],
        buffer_minor=b["buffer_minor"], horizon_end=date.fromisoformat(b["horizon_end"]), input_version=b["input_version"],
        events=events, settlements=settlements,
    )


def bump_input_version(conn, actor: Actor, reason: str) -> int:
    """New input version; pending approvals bound to the old version are invalidated."""
    conn.execute("UPDATE businesses SET input_version = input_version + 1 WHERE tenant_id = ?", (actor.tenant_id,))
    v = conn.execute("SELECT input_version FROM businesses WHERE tenant_id = ?", (actor.tenant_id,)).fetchone()[0]
    stale = conn.execute("SELECT action_id FROM actions WHERE tenant_id = ? AND state IN ('prepared','awaiting_approval','approved')",
                         (actor.tenant_id,)).fetchall()
    for s in stale:
        conn.execute("UPDATE actions SET state='cancelled', failure_code='VERSION_CONFLICT', failure_reason=?, updated_at=? WHERE action_id=?",
                     (f"Input version changed to {v} ({reason}); re-prepare and re-approve.", utcnow_iso(), s["action_id"]))
        conn.execute("UPDATE approvals SET state='invalidated' WHERE action_id = ? AND state='active'", (s["action_id"],))
        audit(conn, actor.tenant_id, "system", None, "approval_invalidated", action_id=s["action_id"], decision_code="VERSION_CONFLICT",
              detail={"new_input_version": v, "reason": reason})
    audit(conn, actor.tenant_id, "user", actor.user_id, "input_version_changed", detail={"input_version": v, "reason": reason})
    return v


# ---------------------------------------------------------------- evidence

def _issues_for(r) -> list[dict]:
    issues = []
    if r["date"] is None:
        issues.append({"field": "date", "severity": "critical", "message": "Date is missing. Add the expected cash date to complete the decision."})
    if r["amount_minor"] is None:
        issues.append({"field": "amount_cny", "severity": "critical", "message": "Amount is missing. Add the cash amount to complete the decision."})
    return issues


def evidence_list(actor: Actor) -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM cash_events WHERE tenant_id = ? ORDER BY date IS NULL, date, event_id", (actor.tenant_id,)).fetchall()
    settled = {}
    acct = active_account(actor.tenant_id)
    if acct:
        for s in conn.execute("SELECT event_id, SUM(amount_minor) a FROM settlements WHERE tenant_id=? AND account_id=? GROUP BY event_id",
                              (actor.tenant_id, acct["account_id"])):
            settled[s["event_id"]] = s["a"]
    records = []
    for r in rows:
        records.append({
            "event_id": r["event_id"], "date": r["date"], "direction": r["direction"], "amount_minor": r["amount_minor"],
            "currency": r["currency"], "category": r["category"], "counterparty_id": r["counterparty_id"],
            "source_document_id": r["source_document_id"], "source_ref": r["source_ref"], "confirmation_status": r["confirmation_status"],
            "description": r["description"], "order_id": r["order_id"], "record_version": r["record_version"],
            "settled_minor": settled.get(r["event_id"], 0), "issues": _issues_for(r), "original": json.loads(r["original_json"]),
        })
    sources = [dict(s) for s in conn.execute(
        "SELECT source_id, label, sha256, source_type, created_at FROM sources WHERE tenant_id = ? ORDER BY created_at", (actor.tenant_id,))]
    return {"records": records, "sources": sources,
            "blocking_issue_count": sum(1 for r in records for i in r["issues"] if i["severity"] == "critical")}


def evidence_detail(actor: Actor, event_id: str) -> dict:
    conn = get_conn()
    r = conn.execute("SELECT * FROM cash_events WHERE tenant_id = ? AND event_id = ?", (actor.tenant_id, event_id)).fetchone()
    if not r:
        raise not_found("Record")
    edits = [dict(e) for e in conn.execute("SELECT field, old_value, new_value, actor, ts, input_version FROM record_edits "
                                           "WHERE tenant_id=? AND event_id=? ORDER BY edit_id", (actor.tenant_id, event_id))]
    src = conn.execute("SELECT source_id, label, sha256, source_type, created_at FROM sources WHERE tenant_id=? AND source_id=?",
                       (actor.tenant_id, r["source_id"])).fetchone()
    d = next(x for x in evidence_list(actor)["records"] if x["event_id"] == event_id)
    d["edits"] = edits
    d["source"] = dict(src) if src else None
    return d


def correct_record(actor: Actor, event_id: str, changes: dict, expected_record_version: int) -> dict:
    require_owner(actor)
    bad = set(changes) - EDITABLE_FIELDS
    if bad:
        raise AppError("VALIDATION_ERROR", "Some fields cannot be edited.", field_errors={f: "not editable" for f in bad})
    conn = get_conn()
    with write_tx(conn):
        r = conn.execute("SELECT * FROM cash_events WHERE tenant_id = ? AND event_id = ?", (actor.tenant_id, event_id)).fetchone()
        if not r:
            raise not_found("Record")
        if r["record_version"] != expected_record_version:
            raise AppError("VERSION_CONFLICT", "This record changed since you opened it. Reload and try again.", 409)
        current = {k: r[k] for k in COLUMNS if k != "amount_cny"}
        current["amount_cny"] = None if r["amount_minor"] is None else f"{r['amount_minor'] / 100:.2f}"
        merged = {**current, **{k: ("" if v is None else str(v)) for k, v in changes.items()}}
        n, issues = normalize_row(merged)
        errors = {i["field"]: i["message"] for i in issues if i["severity"] == "error"}
        if errors:
            raise AppError("VALIDATION_ERROR", "Correction is not valid.", field_errors=errors)
        if "confirmation_status" not in changes and n["confirmation_status"] != "missing":
            n["confirmation_status"] = "user_confirmed"
        new_version = bump_input_version(conn, actor, f"correction of {event_id}")
        for f in ("date", "direction", "amount_minor", "counterparty_id", "category", "confirmation_status", "description"):
            old = r[f]
            if old != n[f]:
                conn.execute("INSERT INTO record_edits (tenant_id, event_id, field, old_value, new_value, actor, ts, input_version) VALUES (?,?,?,?,?,?,?,?)",
                             (actor.tenant_id, event_id, f, None if old is None else str(old), None if n[f] is None else str(n[f]),
                              actor.username, utcnow_iso(), new_version))
        conn.execute("UPDATE cash_events SET date=?, direction=?, amount_minor=?, counterparty_id=?, category=?, confirmation_status=?, description=?, "
                     "record_version = record_version + 1 WHERE tenant_id=? AND event_id=?",
                     (n["date"], n["direction"], n["amount_minor"], n["counterparty_id"] or None, n["category"], n["confirmation_status"],
                      n["description"], actor.tenant_id, event_id))
        audit(conn, actor.tenant_id, "user", actor.user_id, "record_corrected", detail={"event_id": event_id, "fields": sorted(changes)})
    return evidence_detail(actor, event_id)


# ---------------------------------------------------------------- imports

def preview_import(actor: Actor, filename: str, data: bytes, order_id: str | None = None) -> dict:
    require_owner(actor)
    try:
        rows = parse_csv(data, filename)
    except ImportRejected as exc:
        raise AppError(exc.code, str(exc)) from exc
    conn = get_conn()
    existing = {r["event_id"]: dict(r) for r in conn.execute("SELECT * FROM cash_events WHERE tenant_id = ?", (actor.tenant_id,))}
    _classify(rows, existing)
    b = business(actor)
    import_id = "imp_" + secrets.token_hex(6)
    with write_tx(conn):
        conn.execute("INSERT INTO imports (import_id, tenant_id, filename, sha256, status, rows_json, base_version, created_at, order_id) VALUES (?,?,?,?,?,?,?,?,?)",
                     (import_id, actor.tenant_id, filename, hashlib.sha256(data).hexdigest(), "staged", json.dumps(rows),
                      b["input_version"], utcnow_iso(), order_id))
        conn.execute("INSERT INTO sources (source_id, tenant_id, label, sha256, source_type, raw_text, created_at) VALUES (?,?,?,?,?,?,?)",
                     ("src_" + import_id, actor.tenant_id, filename, hashlib.sha256(data).hexdigest(), "csv_upload", data.decode("utf-8-sig"), utcnow_iso()))
        audit(conn, actor.tenant_id, "user", actor.user_id, "import_previewed", detail={"import_id": import_id, "rows": len(rows)})
    return import_summary(actor, import_id)


def _classify(rows: list[dict], existing: dict) -> None:
    for r in rows:
        n = r["normalized"]
        has_error = any(i["severity"] == "error" for i in r["issues"])
        dup = compare_with_existing(n, existing.get(n["event_id"]))
        r["duplicate"] = dup
        if has_error:
            r["status"] = "invalid"
        elif dup == "conflict":
            r["status"] = "conflict"
            if not any(i["field"] == "event_id" and "conflicts" in i["message"] for i in r["issues"]):
                r["issues"].append({"field": "event_id", "severity": "review",
                                    "message": "An existing record with this event_id has different economic values; correct the row or remove it."})
        elif dup == "identical":
            r["status"] = "duplicate_identical"
        else:
            r["status"] = "valid"


def import_summary(actor: Actor, import_id: str) -> dict:
    row = get_conn().execute("SELECT * FROM imports WHERE tenant_id = ? AND import_id = ?", (actor.tenant_id, import_id)).fetchone()
    if not row:
        raise not_found("Import")
    rows = json.loads(row["rows_json"])
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    blocking = counts.get("invalid", 0) + counts.get("conflict", 0)
    return {"import_id": import_id, "filename": row["filename"], "status": row["status"], "base_version": row["base_version"],
            "committed_version": row["committed_version"], "counts": counts, "can_commit": row["status"] == "staged" and blocking == 0,
            "rows": rows}


def correct_staged_row(actor: Actor, import_id: str, row_number: int, changes: dict) -> dict:
    require_owner(actor)
    conn = get_conn()
    with write_tx(conn):
        imp = conn.execute("SELECT * FROM imports WHERE tenant_id = ? AND import_id = ?", (actor.tenant_id, import_id)).fetchone()
        if not imp or imp["status"] != "staged":
            raise not_found("Staged import")
        rows = json.loads(imp["rows_json"])
        target = next((r for r in rows if r["row_number"] == row_number), None)
        if not target:
            raise not_found("Row")
        if changes.get("_remove"):
            rows = [r for r in rows if r["row_number"] != row_number]
        else:
            raw = {**target["original"], **{k: str(v) for k, v in changes.items() if k in COLUMNS}}
            n, issues = normalize_row(raw)
            if not n["source_ref"]:
                n["source_ref"] = f"{imp['filename']}#row{row_number}"
            target["corrected"] = {k: v for k, v in changes.items() if k in COLUMNS}
            target["normalized"], target["issues"] = n, issues
        existing = {r["event_id"]: dict(r) for r in conn.execute("SELECT * FROM cash_events WHERE tenant_id = ?", (actor.tenant_id,))}
        _classify(rows, existing)
        conn.execute("UPDATE imports SET rows_json = ? WHERE import_id = ?", (json.dumps(rows), import_id))
        audit(conn, actor.tenant_id, "user", actor.user_id, "import_row_corrected", detail={"import_id": import_id, "row": row_number})
    return import_summary(actor, import_id)


def commit_import(actor: Actor, import_id: str, expected_version: int) -> dict:
    require_owner(actor)
    conn = get_conn()
    with write_tx(conn):
        imp = conn.execute("SELECT * FROM imports WHERE tenant_id = ? AND import_id = ?", (actor.tenant_id, import_id)).fetchone()
        if not imp:
            raise not_found("Import")
        if imp["status"] == "committed":
            return {"import_id": import_id, "status": "committed", "input_version": imp["committed_version"], "created": 0, "unchanged": 0}
        b = conn.execute("SELECT * FROM businesses WHERE tenant_id = ?", (actor.tenant_id,)).fetchone()
        if b["input_version"] != expected_version:
            raise AppError("VERSION_CONFLICT", f"Data changed (now version {b['input_version']}); re-check the preview.", 409)
        rows = json.loads(imp["rows_json"])
        existing = {r["event_id"]: dict(r) for r in conn.execute("SELECT * FROM cash_events WHERE tenant_id = ?", (actor.tenant_id,))}
        _classify(rows, existing)
        blocking = [r for r in rows if r["status"] in ("invalid", "conflict")]
        if blocking:
            raise AppError("VALIDATION_ERROR", f"{len(blocking)} row(s) need correction or removal before commit; nothing was committed.",
                           field_errors={str(r["row_number"]): "; ".join(i["message"] for i in r["issues"]) for r in blocking})
        new_rows = [r for r in rows if r["status"] == "valid"]
        version = b["input_version"]
        if new_rows:
            version = bump_input_version(conn, actor, f"import {import_id}")
            for r in new_rows:
                n = r["normalized"]
                conn.execute(
                    "INSERT INTO cash_events (tenant_id, event_id, business_id, date, direction, amount_minor, currency, category, counterparty_id, "
                    "source_document_id, source_ref, confirmation_status, description, order_id, source_id, original_json, created_in_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (actor.tenant_id, n["event_id"], b["business_id"], n["date"], n["direction"], n["amount_minor"], n["currency"], n["category"],
                     n["counterparty_id"] or None, n["source_document_id"], n["source_ref"], n["confirmation_status"], n["description"],
                     imp["order_id"], "src_" + import_id, json.dumps(r["original"]), version))
        conn.execute("UPDATE imports SET status='committed', committed_version=? WHERE import_id=?", (version, import_id))
        audit(conn, actor.tenant_id, "user", actor.user_id, "import_committed",
              detail={"import_id": import_id, "created": len(new_rows), "unchanged_duplicates": sum(1 for r in rows if r["status"] == "duplicate_identical"),
                      "input_version": version})
    return {"import_id": import_id, "status": "committed", "input_version": version, "created": len(new_rows),
            "unchanged": sum(1 for r in rows if r["status"] == "duplicate_identical")}


def load_example(actor: Actor) -> dict:
    """Load the labelled synthetic reference case (idempotent: exact duplicates are no-ops)."""
    require_owner(actor)
    b = read_json("business.json")
    results = []
    for fname, order_id in (("cash_events.csv", None), ("order_ORDER-001.csv", b["order"]["order_id"])):
        data = (FIXTURES_DIR / fname).read_bytes()
        prev = preview_import(actor, fname, data, order_id)
        if not prev["can_commit"]:
            raise AppError("VALIDATION_ERROR", f"Synthetic example {fname} conflicts with existing records; reset the demo workspace.")
        results.append(commit_import(actor, prev["import_id"], business(actor)["input_version"]))
    return {"loaded": results, "input_version": business(actor)["input_version"], "label": "Synthetic example loaded"}
