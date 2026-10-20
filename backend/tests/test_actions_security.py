"""Controlled sandbox action, approval, idempotency and authorization (criteria 11-21, 24)."""
import json
import threading

from app import config, db
from app.main import app

from .conftest import Api, accept_combined_and_init, prepare


def approve(api, a):
    return api.post(f"/api/actions/{a['action_id']}/approve", json={"payload_hash": a["payload_hash"]})


def test_sandbox_bootstrap_is_176000(owner):
    sbx = accept_combined_and_init(owner)
    assert sbx["available_minor"] == 17_600_000 and sbx["simulated_date"] == "2026-10-04"
    # initialization is idempotent and does not rewrite history
    assert owner.post("/api/sandbox/initialize").json()["account_id"] == sbx["account_id"]


def test_unapproved_execution_rejected(owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    assert a["state"] == "awaiting_approval" and all(c["passed"] for c in a["policy_checks"])
    r = owner.post(f"/api/actions/{a['action_id']}/execute")
    assert r.status_code == 409 and r.json()["code"] == "APPROVAL_REQUIRED"
    assert owner.get("/api/sandbox").json()["available_minor"] == 17_600_000


def test_approved_execution_settles_once_and_is_idempotent(owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    assert approve(owner, a).json()["state"] == "approved"
    r = owner.post(f"/api/actions/{a['action_id']}/execute", headers={"Idempotency-Key": "k1"}).json()
    rc = r["receipt"]
    assert r["state"] == "succeeded" and rc["balance_before_minor"] == 17_600_000 and rc["balance_after_minor"] == 10_600_000
    again = owner.post(f"/api/actions/{a['action_id']}/execute", headers={"Idempotency-Key": "k1"}).json()
    assert again["receipt"]["receipt_id"] == rc["receipt_id"]
    assert owner.get(f"/api/actions/{a['action_id']}").json()["state"] == "succeeded"
    assert owner.get("/api/sandbox").json()["available_minor"] == 10_600_000
    stl = [s for s in owner.get("/api/export").json()["settlements"] if s["action_id"]]
    assert len(stl) == 1 and stl[0]["event_id"] == "ORD-001-MAT-1"
    # forecast does not count the payment twice; deferred half remains scheduled for day 46
    f = owner.post("/api/forecasts", json={"scenario_id": "combined_terms"}).json()
    assert f["metrics"]["lowest_balance_minor"] == 4_600_000 and f["metrics"]["ending_balance_minor"] == 24_000_000
    day46 = next(d for d in f["daily"] if d["day"] == 46)
    assert day46["outflow_minor"] == 7_000_000 and "ORD-001-MAT-2" in day46["event_refs"]
    # a second payment against the settled obligation is blocked
    b = prepare(owner, key="k2").json()
    assert b["state"] == "blocked" and b["failure_code"] == "POLICY_BLOCKED"


def test_concurrent_identical_execution_single_effect(owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    approve(owner, a)
    results, errors = [], []

    def go():
        try:
            from fastapi.testclient import TestClient
            c = TestClient(app, headers={"Origin": "http://localhost:8000"}, cookies=owner.c.cookies)
            results.append(c.post(f"/api/actions/{a['action_id']}/execute", headers={"X-CSRF-Token": owner.csrf}).json())
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            db.reset_thread_connections()

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(results) == 8
    assert {r["state"] for r in results} == {"succeeded"} and len({r["receipt"]["receipt_id"] for r in results}) == 1
    exp = owner.get("/api/export").json()
    assert len([s for s in exp["settlements"] if s["action_id"]]) == 1
    assert len([l for l in exp["sandbox_ledger"] if l["reason"] == "sandbox_payment"]) == 1
    assert owner.get("/api/sandbox").json()["available_minor"] == 10_600_000


def test_idempotency_key_reuse_with_different_payload_conflicts(owner):
    accept_combined_and_init(owner)
    a = prepare(owner, key="same").json()
    assert prepare(owner, key="same").json()["action_id"] == a["action_id"]
    r = prepare(owner, amount="60000.00", key="same")
    assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    approve(owner, a)
    r = owner.post(f"/api/actions/{a['action_id']}/execute", headers={"Idempotency-Key": "other"})
    assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_CONFLICT"


def _tamper(action_id, field, value):
    conn = db.connect(config.DB_PATH)
    row = conn.execute("SELECT payload_json FROM actions WHERE action_id=?", (action_id,)).fetchone()
    p = json.loads(row[0])
    p[field] = value
    conn.execute("UPDATE actions SET payload_json=? WHERE action_id=?", (json.dumps(p, sort_keys=True), action_id))
    conn.close()


def test_stale_approval_amount_or_recipient_tampering(owner):
    accept_combined_and_init(owner)
    for i, (field, value) in enumerate((("amount_minor", 6_900_000), ("recipient_id", "SUP-OTH-201"))):
        a = prepare(owner, key=f"t{i}").json()
        approve(owner, a)
        _tamper(a["action_id"], field, value)
        r = owner.post(f"/api/actions/{a['action_id']}/execute")
        assert r.json()["code"] == "VERSION_CONFLICT", r.json()
    assert owner.get("/api/sandbox").json()["available_minor"] == 17_600_000


def test_stale_approval_input_change(owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    approve(owner, a)
    rec = owner.get("/api/evidence/E-005").json()
    owner.patch("/api/records/E-005", json={"changes": {"amount_cny": "30500.00"}, "expected_record_version": rec["record_version"]})
    r = owner.post(f"/api/actions/{a['action_id']}/execute")
    assert r.json()["code"] == "VERSION_CONFLICT" and owner.get(f"/api/actions/{a['action_id']}").json()["state"] == "cancelled"


def test_stale_approval_account_and_policy_change(owner, monkeypatch):
    accept_combined_and_init(owner)
    a = prepare(owner, key="acc").json()
    approve(owner, a)
    conn = db.connect(config.DB_PATH)
    conn.execute("UPDATE sandbox_accounts SET ledger_version = ledger_version + 1")
    conn.close()
    assert owner.post(f"/api/actions/{a['action_id']}/execute").json()["code"] == "VERSION_CONFLICT"
    b = prepare(owner, key="pol").json()
    approve(owner, b)
    monkeypatch.setitem(config.POLICY, "policy_version", "demo-policy-2")
    assert owner.post(f"/api/actions/{b['action_id']}/execute").json()["code"] == "VERSION_CONFLICT"


def test_approval_rejects_mismatched_reviewed_hash(owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    r = owner.post(f"/api/actions/{a['action_id']}/approve", json={"payload_hash": "0" * 64})
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"


def test_approval_expires_with_injected_clock(owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    approve(owner, a)
    db.clock.advance(config.POLICY["approval_ttl_seconds"] + 1)
    r = owner.post(f"/api/actions/{a['action_id']}/execute")
    assert r.json()["code"] == "APPROVAL_EXPIRED" and owner.get(f"/api/actions/{a['action_id']}").json()["state"] == "expired"
    assert owner.get("/api/sandbox").json()["available_minor"] == 17_600_000


def test_per_payment_limit_blocks_120000_even_with_cash(owner):
    accept_combined_and_init(owner)
    a = prepare(owner, amount="120000.00", key="big").json()
    checks = {c["check"]: c for c in a["policy_checks"]}
    assert a["state"] == "blocked" and not checks["per_payment_limit"]["passed"] and checks["available_cash_and_buffer"]["passed"]
    assert a["failure_code"] == "POLICY_BLOCKED"
    assert approve(owner, a).status_code == 409


def test_unknown_and_other_tenant_recipients_rejected(owner):
    accept_combined_and_init(owner)
    for i, rid in enumerate(("ATTACKER-0001", "SUP-OTHER-900")):
        a = prepare(owner, recipient=rid, key=f"r{i}").json()
        assert a["state"] == "blocked" and a["failure_code"] == "RECIPIENT_NOT_ALLOWED"


def test_red_operations_blocked(owner):
    accept_combined_and_init(owner)
    r = owner.post("/api/actions/prepare", json={"scenario_id": "illustrative_loan", "obligation_event_id": "LOAN-DRAW", "recipient_id": "SUP-MAT-001",
                                                 "amount": "110000.00", "idempotency_key": "loan", "action_type": "real_borrowing"})
    assert r.status_code == 403 and r.json()["code"] == "POLICY_BLOCKED"


def test_viewer_and_other_tenant_cannot_approve_or_execute(owner, viewer, other_owner):
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    assert viewer.get(f"/api/actions/{a['action_id']}").status_code == 200  # viewer can read
    assert approve(viewer, a).status_code == 403
    assert viewer.post(f"/api/actions/{a['action_id']}/execute").status_code == 403
    r = approve(other_owner, a)
    assert r.status_code == 404 and r.json()["user_message"] == "Action not found."
    approve(owner, a)
    assert other_owner.post(f"/api/actions/{a['action_id']}/execute").status_code == 404
    assert viewer.post(f"/api/actions/{a['action_id']}/execute").status_code == 403
    assert owner.get("/api/sandbox").json()["available_minor"] == 17_600_000


def test_cross_tenant_record_access_denied(owner, other_owner):
    owner.post("/api/workspace/load-example")
    assert other_owner.get("/api/evidence/E-001").status_code == 404
    assert other_owner.patch("/api/records/E-001", json={"changes": {"amount_cny": "1.00"}, "expected_record_version": 1}).status_code == 404
    assert owner.get("/api/evidence/OTH-001").status_code == 404
    ids = {r["event_id"] for r in other_owner.get("/api/evidence").json()["records"]}
    assert ids == {"OTH-001", "OTH-002"}


def test_csrf_origin_and_auth_required(owner, db_path):
    from fastapi.testclient import TestClient
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    r = owner.c.post(f"/api/actions/{a['action_id']}/approve", json={"payload_hash": a["payload_hash"]})  # no CSRF header
    assert r.status_code == 403 and r.json()["code"] == "CSRF_FAILED"
    r = owner.c.post(f"/api/actions/{a['action_id']}/approve", json={"payload_hash": a["payload_hash"]},
                     headers={"X-CSRF-Token": owner.csrf, "Origin": "https://evil.example"})
    assert r.status_code == 403
    assert TestClient(app).get("/api/workspace").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"username": "owner@demo-gba", "password": "wrong"}).status_code == 401


def test_viewer_cannot_mutate(viewer):
    assert viewer.post("/api/workspace/load-example").status_code == 403
    assert viewer.post("/api/scenarios/combined_terms/conditions", json={"condition_id": "buyer_deposit_30pct", "accept": True}).status_code == 403


def test_export_contains_versions_and_no_secrets(owner, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-appear")
    accept_combined_and_init(owner)
    a = prepare(owner).json()
    approve(owner, a)
    owner.post(f"/api/actions/{a['action_id']}/execute")
    exp = owner.get("/api/export").json()
    assert exp["business"]["input_version"] >= 1 and exp["forecast_runs"] and exp["forecast_runs"][0]["assumptions"]
    assert exp["approvals"][0]["state"] == "consumed" and exp["actions"][0]["receipt"]["balance_after_minor"] == 10_600_000
    blob = owner.get("/api/export?format=zip").content
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(blob))
    text = "".join(z.read(n).decode() for n in z.namelist())
    for secret in ("sk-ant-should-never-appear", "password_hash", "$2b$", "csrf_token", "token_hash", "execution_capability_hash"):
        assert secret not in text
    assert {"evidence.json", "cash_events.csv", "audit.csv"} <= set(z.namelist())
