"""Persistent application flow, imports, evidence and decisions."""
from app.config import FIXTURES_DIR

from .conftest import Api, accept_combined_and_init


def test_load_example_compare_and_decision(owner):
    r = owner.post("/api/workspace/load-example")
    assert r.status_code == 200 and r.json()["input_version"] == 3
    comp = owner.post("/api/comparisons", json={}).json()
    rows = {s["scenario_id"]: s for s in comp["scenarios"]}
    assert rows["current_terms"]["lowest_balance_minor"] == -9_000_000 and rows["combined_terms"]["terms_status"] == "conditional"
    assert comp["decision"]["decision_code"] == "conditional_terms"
    assert all(f["run_id"] in comp["runs"] for f in comp["decision"]["fact_refs"])
    # load again: exact duplicates are idempotent
    again = owner.post("/api/workspace/load-example").json()
    assert all(x["created"] == 0 for x in again["loaded"]) and len(owner.get("/api/evidence").json()["records"]) == 9


def test_selecting_or_comparing_does_not_accept_terms_or_change_cash(owner):
    owner.post("/api/workspace/load-example")
    owner.post("/api/comparisons", json={})
    owner.post("/api/forecasts", json={"scenario_id": "combined_terms"})
    ws = owner.get("/api/workspace").json()
    assert all(c["status"] in ("proposed", "not_assessed") for c in ws["conditions"]) and ws["sandbox"] is None
    assert owner.post("/api/sandbox/initialize").json()["code"] == "POLICY_BLOCKED"


def test_credit_eligibility_cannot_be_accepted(owner):
    owner.post("/api/workspace/load-example")
    r = owner.post("/api/scenarios/illustrative_loan/conditions", json={"condition_id": "credit_eligibility", "accept": True})
    assert r.status_code == 403 and r.json()["code"] == "POLICY_BLOCKED"


def test_missing_receipt_date_needs_information_and_blocks_action(owner):
    accept_combined_and_init(owner)
    rec = owner.get("/api/evidence/ORD-001-RCPT").json()
    r = owner.patch("/api/records/ORD-001-RCPT", json={"changes": {"date": None}, "expected_record_version": rec["record_version"]})
    assert r.status_code == 200 and r.json()["confirmation_status"] == "missing"
    comp = owner.post("/api/comparisons", json={}).json()
    assert comp["decision"]["decision_code"] == "needs_information"
    # the deposit scenario replaces the receipt, but current terms and the original record remain incomplete
    a = owner.post("/api/actions/prepare", json={"scenario_id": "current_terms", "obligation_event_id": "ORD-001-MAT", "recipient_id": "SUP-MAT-001",
                                                 "amount": "70000.00", "idempotency_key": "x"}).json()
    assert a["state"] == "blocked"
    assert any(c["check"] == "plan_cash_policy" and not c["passed"] for c in a["policy_checks"])


def test_edit_records_history_and_persists_recalculation(owner, db_path):
    owner.post("/api/workspace/load-example")
    rec = owner.get("/api/evidence/E-003").json()
    r = owner.patch("/api/records/E-003", json={"changes": {"amount_cny": "45000.00"}, "expected_record_version": rec["record_version"]})
    assert r.status_code == 200
    d = r.json()
    assert d["edits"][0]["old_value"] == "4000000" and d["edits"][0]["new_value"] == "4500000" and d["original"]["amount_cny"] == "40000.00"
    stale = owner.patch("/api/records/E-003", json={"changes": {"amount_cny": "1.00"}, "expected_record_version": rec["record_version"]})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    # simulate a backend restart: drop connections and use a new client
    from app import db
    db.reset_thread_connections()
    fresh = Api("owner@demo-gba")
    f = fresh.post("/api/forecasts", json={"scenario_id": "current_terms"}).json()
    assert f["metrics"]["lowest_balance_minor"] == -9_500_000
    assert fresh.get(f"/api/forecasts/{f['run_id']}").json()["metrics"]["lowest_balance_minor"] == -9_500_000


def upload(api, name, content=None):
    data = content if content is not None else (FIXTURES_DIR / "import_samples" / name).read_bytes()
    return api.c.post("/api/imports/preview", files={"file": (name, data, "text/csv")}, headers={"X-CSRF-Token": api.csrf})


def test_import_exact_duplicate_creates_no_event(owner):
    owner.post("/api/workspace/load-example")
    v = owner.get("/api/workspace").json()["business"]["input_version"]
    p = upload(owner, "duplicate_exact.csv").json()
    assert p["counts"] == {"duplicate_identical": 1} and p["can_commit"]
    c = owner.post(f"/api/imports/{p['import_id']}/commit", json={"expected_version": v}).json()
    assert c["created"] == 0 and c["input_version"] == v


def test_import_conflicting_duplicate_requires_review(owner):
    owner.post("/api/workspace/load-example")
    v = owner.get("/api/workspace").json()["business"]["input_version"]
    p = upload(owner, "duplicate_conflict.csv").json()
    assert p["counts"] == {"conflict": 1} and not p["can_commit"]
    r = owner.post(f"/api/imports/{p['import_id']}/commit", json={"expected_version": v})
    assert r.status_code == 400 and "nothing was committed" in r.json()["user_message"]
    fixed = owner.patch(f"/api/imports/{p['import_id']}/rows/2", json={"changes": {"amount_cny": "60000.00", "source_ref": "cash_events.csv#row2"}}).json()
    assert fixed["counts"] == {"duplicate_identical": 1} and fixed["can_commit"]


def test_import_validation_and_correction(owner):
    owner.post("/api/workspace/load-example")
    p = upload(owner, "invalid_rows.csv").json()
    by_row = {r["row_number"]: r for r in p["rows"]}
    assert [by_row[i]["status"] for i in range(2, 7)] == ["invalid"] * 5
    assert by_row[7]["status"] == "valid"  # formula text in description is data; escaped on export
    assert not p["can_commit"]
    for n in (2, 3, 5, 6):
        owner.patch(f"/api/imports/{p['import_id']}/rows/{n}", json={"changes": {"_remove": True}})
    fixed = owner.patch(f"/api/imports/{p['import_id']}/rows/4", json={"changes": {"amount_cny": "100.01"}}).json()
    assert fixed["can_commit"] and fixed["counts"] == {"valid": 2}
    v = owner.get("/api/workspace").json()["business"]["input_version"]
    assert owner.post(f"/api/imports/{p['import_id']}/commit", json={"expected_version": v}).json()["created"] == 2
    csv_text = owner.get("/api/export?format=csv").text
    assert "'=HYPERLINK" in csv_text and ",100.01," in csv_text


def test_import_rejects_bad_files(owner):
    assert upload(owner, "x.txt", b"a,b").json()["code"] == "VALIDATION_ERROR"
    assert "UTF-8" in upload(owner, "x.csv", b"\xff\xfe\x00bad").json()["user_message"]
    assert "columns" in upload(owner, "x.csv", b"a,b\n1,2\n").json()["user_message"]


def test_same_amount_distinct_ids_are_not_duplicates(owner):
    owner.post("/api/workspace/load-example")
    p = upload(owner, "same_amount_distinct_ids.csv").json()
    assert p["counts"] == {"valid": 2}


def test_horizon_rejection_explicit(owner):
    owner.post("/api/workspace/load-example")
    r = owner.post("/api/forecasts", json={"scenario_id": "supplier_deferral", "horizon_end": "2026-11-01", "extend_horizon": False})
    assert r.status_code == 400 and "hides modeled obligations" in r.json()["user_message"]
    r = owner.post("/api/forecasts", json={"scenario_id": "supplier_deferral", "horizon_end": "2026-11-01"}).json()
    assert r["horizon_end"] == "2026-11-16"


def test_health_has_no_secrets(db_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret-value")
    body = TestClient(app).get("/api/health").text
    assert "sk-test" not in body and '"live_model_configured":true' in body
