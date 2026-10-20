"""Reference calculation tests (acceptance criteria 1-5, 8-10)."""
import csv
import json
from dataclasses import replace
from datetime import date

import pytest

from app.config import FIXTURES_DIR
from app.domain.engine import EngineError, LedgerEvent, Settlement, project, run_scenario, assess_financing
from app.domain.money import MoneyError, parse_amount_minor
from app.fixtures_loader import catalogue, reference_inputs, scenario_defs

EXPECTED = json.loads((FIXTURES_DIR / "expected_results.json").read_text())["scenarios"]
SCENARIOS = list(EXPECTED)


def run(sid, inputs=None, conditions=None):
    return run_scenario(inputs or reference_inputs(), sid, scenario_defs(), catalogue(), conditions or {})


@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_metrics_match_expected_results(sid):
    m, exp = run(sid), EXPECTED[sid]
    assert m["metrics"]["lowest_balance_minor"] == exp["lowest_balance_minor"]
    assert m["metrics"]["lowest_balance_date"] == exp["lowest_balance_date"]
    assert m["metrics"]["first_negative_day"] == exp["first_negative_day"]
    assert m["metrics"]["required_support_minor"] == exp["required_support_minor"]
    assert m["metrics"]["ending_balance_minor"] == exp["ending_balance_minor"]
    assert m["economics"]["contribution_after_financing_minor"] == exp["contribution_after_financing_minor"]


def test_every_daily_balance_row_matches():
    with open(FIXTURES_DIR / "expected_daily_balances.csv") as f:
        rows = list(csv.DictReader(f))
    results = {sid: {d["day"]: d for d in run(sid)["daily"]} for sid in SCENARIOS}
    assert len(rows) == 6 * 47
    for r in rows:
        got = results[r["scenario_id"]][int(r["day"])]
        assert got["date"] == r["date"]
        assert got["closing_minor"] == int(r["closing_balance_minor"]), r


def test_current_terms_shortfall():
    m = run("current_terms")["metrics"]
    assert (m["first_negative_day"], m["lowest_balance_day"], m["lowest_balance_minor"], m["required_support_minor"]) == (3, 10, -9_000_000, 11_000_000)


def test_deposit_replaces_final_receipt_and_deferral_keeps_liability():
    dep = run("buyer_deposit")
    ids = {e["event_id"]: e for e in dep["ledger"]}
    assert "ORD-001-RCPT" not in ids and ids["ORD-001-RCPT-BAL"]["amount_minor"] == 15_400_000 and ids["ORD-001-DEP"]["amount_minor"] == 6_600_000
    deferral = {e["event_id"]: e for e in run("supplier_deferral")["ledger"]}
    assert "ORD-001-MAT" not in deferral
    assert deferral["ORD-001-MAT-2"]["date"] == "2026-11-16" and deferral["ORD-001-MAT-2"]["amount_minor"] == 7_000_000
    assert run("supplier_deferral")["metrics"]["ending_balance_minor"] == 24_000_000


def test_combined_terms_conditional_until_accepted():
    r = run("combined_terms")
    assert r["metrics"]["lowest_balance_minor"] == 4_600_000 and r["metrics"]["ending_balance_minor"] == 24_000_000
    assert r["terms_status"] == "conditional" and len(r["unresolved_conditions"]) == 2
    r2 = run("combined_terms", conditions={"buyer_deposit_30pct": "accepted"})
    assert r2["terms_status"] == "conditional"
    r3 = run("combined_terms", conditions={"buyer_deposit_30pct": "accepted", "supplier_deferral_50pct": "accepted"})
    assert r3["terms_status"] == "accepted"


def test_loan_costs():
    r = run("illustrative_loan")
    f = r["financing"]
    assert (f["interest_minor"], f["total_cost_minor"]) == (155_507, 205_507)
    assert r["metrics"]["ending_balance_minor"] == 23_794_493
    assert r["economics"]["contribution_after_financing_minor"] == 5_794_493
    assert r["economics"]["borrowed_principal_minor"] == 11_000_000 and r["metrics"]["residual_support_after_financing_minor"] == 0
    # credit eligibility can never be accepted by the owner
    assert run("illustrative_loan", conditions={"credit_eligibility": "accepted"})["terms_status"] == "conditional"


def test_missing_receipt_date_is_incomplete_not_zero():
    inputs = reference_inputs()
    inputs.events = [replace(e, date=None) if e.event_id == "ORD-001-RCPT" else e for e in inputs.events]
    r = run("current_terms", inputs)
    assert r["complete"] is False and r["terms_status"] == "incomplete"
    assert r["issues"][0]["event_id"] == "ORD-001-RCPT" and r["issues"][0]["fields"] == ["date"]


def test_partial_settlement_counts_obligation_once():
    inputs = reference_inputs()
    inputs.events = [LedgerEvent("OB-1", date(2026, 10, 20), "out", 1_000_000)]
    inputs.settlements = [Settlement("S-1", "OB-1", date(2026, 10, 5), 400_000)]
    r = project(inputs, inputs.events)
    total_out = sum(d["outflow_minor"] for d in r["daily"])
    assert total_out == 1_000_000
    by_date = {d["date"]: d["outflow_minor"] for d in r["daily"]}
    assert by_date["2026-10-05"] == 400_000 and by_date["2026-10-20"] == 600_000


def test_settled_events_not_counted_twice():
    inputs = reference_inputs()
    inputs.settlements = [Settlement("S-1", "E-001", date(2026, 10, 2), 6_000_000), Settlement("S-2", "ORD-001-RCPT", date(2026, 11, 15), 22_000_000)]
    assert run("current_terms", inputs)["metrics"]["ending_balance_minor"] == 24_000_000


def test_horizon_excluding_obligations_rejected_or_extended():
    inputs = reference_inputs()
    events = run("supplier_deferral")  # ensure scenario works
    with pytest.raises(EngineError):
        run_scenario(inputs, "supplier_deferral", scenario_defs(), catalogue(), {}, horizon_end=date(2026, 11, 1), extend_horizon=False)
    r = run_scenario(inputs, "supplier_deferral", scenario_defs(), catalogue(), {}, horizon_end=date(2026, 11, 1))
    assert r["horizon_end"] == "2026-11-16" and any("extended" in a for a in r["assumptions"])
    assert events["horizon_end"] == "2026-11-16"


def test_unsupported_currency_fails_clearly():
    inputs = reference_inputs()
    inputs.events = inputs.events + [LedgerEvent("FX-1", date(2026, 10, 5), "in", 100, currency="USD")]
    with pytest.raises(EngineError, match="only CNY"):
        run("no_order", inputs)


@pytest.mark.parametrize("bad", ["100.005", "=1+1", "-5", "1e5", "", "12,000"])
def test_money_parser_rejects(bad):
    with pytest.raises(MoneyError):
        parse_amount_minor(bad)


def test_money_parser_exact():
    assert parse_amount_minor("70000") == 7_000_000 and parse_amount_minor("0.10") == 10


def test_financing_assessment():
    res = {p["product_id"]: p for p in assess_financing(reference_inputs(), scenario_defs(), catalogue(), {}, "working_capital")}
    assert res["illustrative_working_capital"]["passes_hard_constraints"] is True
    bridge = res["illustrative_short_bridge"]
    assert bridge["passes_hard_constraints"] is False
    assert any("exceeds" in r for r in bridge["reasons"]) and any("Timing" in r for r in bridge["reasons"])
    assert res["illustrative_equipment_only"]["passes_hard_constraints"] is False
    assert all(p["credit_approval"] == "not_assessed" for p in res.values())
