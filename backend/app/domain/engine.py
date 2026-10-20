"""Deterministic daily cash engine.

Pure functions only: no HTTP, database or model SDK imports. Inputs are plain
dataclasses in integer minor units; outputs are JSON-serialisable dicts.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from .money import SUPPORTED_CURRENCY, parse_amount_minor, simple_interest_minor

ENGINE_VERSION = "engine-1.0"


class EngineError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    date: date | None
    direction: str  # "in" | "out"
    amount_minor: int | None
    currency: str = SUPPORTED_CURRENCY
    category: str = ""
    counterparty_id: str | None = None
    source_document_id: str | None = None
    source_ref: str | None = None
    confirmation_status: str = "synthetic"
    order_id: str | None = None
    origin: str = "record"  # record | scenario_term | financing
    replaces_event_id: str | None = None
    condition_id: str | None = None


@dataclass(frozen=True)
class Settlement:
    settlement_id: str
    event_id: str
    actual_date: date
    amount_minor: int
    action_id: str | None = None


@dataclass
class BusinessInputs:
    business_id: str
    opening_date: date
    opening_cash_minor: int
    buffer_minor: int
    horizon_end: date
    input_version: int
    events: list[LedgerEvent]
    settlements: list[Settlement] = field(default_factory=list)


def day_index(opening: date, d: date) -> int:
    return (d - opening).days


# ---------------------------------------------------------------- scenarios

def _resolve_transforms(scenario: dict, all_scenarios: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for t in scenario.get("transformations", []):
        if "ref" in t:
            out.extend(_resolve_transforms(all_scenarios[t["ref"]], all_scenarios))
        else:
            out.append(t)
    return out


def build_scenario_ledger(
    inputs: BusinessInputs,
    scenario_id: str,
    scenario_defs: dict,
    catalogue: list[dict],
    condition_status: dict[str, str],
) -> dict:
    """Apply explicit replacements/additions to the base events for one scenario."""
    all_scen = {s["scenario_id"]: s for s in scenario_defs["scenarios"]}
    if scenario_id not in all_scen:
        raise EngineError("VALIDATION_ERROR", f"unknown scenario '{scenario_id}'")
    scen = all_scen[scenario_id]
    events = [e for e in inputs.events if scen["include_order"] or e.order_id is None]
    applied: list[dict] = []
    financing: dict | None = None
    for t in _resolve_transforms(scen, all_scen):
        if t["type"] == "replace":
            target = t["target_event_id"]
            if not any(e.event_id == target for e in events):
                raise EngineError("MISSING_EVIDENCE", f"scenario {scenario_id} needs event {target}, which is not in the ledger")
            orig = next(e for e in events if e.event_id == target)
            events = [e for e in events if e.event_id != target]
            new_ids = []
            for r in t["replacements"]:
                ev = LedgerEvent(
                    event_id=r["event_id"], date=date.fromisoformat(r["date"]), direction=r["direction"],
                    amount_minor=parse_amount_minor(r["amount_cny"]), category=r["category"],
                    counterparty_id=r.get("counterparty_id"), source_document_id="scenarios.json",
                    source_ref=f"scenarios.json#{scenario_id}/{r['event_id']}", confirmation_status="assumed",
                    order_id=orig.order_id, origin="scenario_term", replaces_event_id=target, condition_id=t.get("condition_id"),
                )
                events.append(ev)
                new_ids.append(ev.event_id)
            applied.append({"type": "replace", "target_event_id": target, "replacement_event_ids": new_ids, "condition_id": t.get("condition_id")})
        elif t["type"] == "loan":
            product = next(p for p in catalogue if p["product_id"] == t["product_id"])
            principal = parse_amount_minor(t["principal_cny"])
            draw, repay = date.fromisoformat(t["draw_date"]), date.fromisoformat(t["repay_date"])
            fin = loan_cash_events(product, principal, draw, repay)
            events.extend(fin["events"])
            financing = fin["summary"]
            applied.append({"type": "loan", "product_id": product["product_id"], "event_ids": [e.event_id for e in fin["events"]]})
    conditions = []
    for cid in scen.get("conditions", []):
        cdef = scenario_defs["conditions"][cid]
        status = cdef.get("fixed_status") or condition_status.get(cid, "proposed")
        conditions.append({"condition_id": cid, "label": cdef["label"], "status": status, "acceptable_by_owner": cdef["acceptable_by_owner"]})
    return {"scenario_id": scenario_id, "label": scen["label"], "events": events, "transformations": applied,
            "conditions": conditions, "financing": financing}


def loan_cash_events(product: dict, principal_minor: int, draw: date, repay: date) -> dict:
    days = (repay - draw).days
    interest = simple_interest_minor(principal_minor, product["annual_simple_rate"], days, product["day_count_basis"])
    fee = parse_amount_minor(product["fee_cny"])
    pid = product["product_id"]
    mk = lambda eid, d, direction, amt, cat: LedgerEvent(  # noqa: E731
        event_id=eid, date=d, direction=direction, amount_minor=amt, category=cat, source_document_id="financing_catalogue.json",
        source_ref=f"financing_catalogue.json#{pid}", confirmation_status="assumed", origin="financing", condition_id="credit_eligibility")
    fee_date = repay if product["fee_timing"] == "at_repayment" else draw
    events = [
        mk("LOAN-DRAW", draw, "in", principal_minor, "loan_draw"),
        mk("LOAN-REPAY", repay, "out", principal_minor, "loan_repayment"),
        mk("LOAN-INTEREST", repay, "out", interest, "loan_interest"),
        mk("LOAN-FEE", fee_date, "out", fee, "loan_fee"),
    ]
    return {"events": events, "summary": {
        "product_id": pid, "label": product["label"], "synthetic": True, "principal_minor": principal_minor,
        "draw_date": draw.isoformat(), "repayment_date": repay.isoformat(), "days": days,
        "annual_simple_rate": product["annual_simple_rate"], "day_count_basis": product["day_count_basis"],
        "interest_minor": interest, "fee_minor": fee, "fee_timing": product["fee_timing"],
        "total_cost_minor": interest + fee,
        "formula": f"{principal_minor/100:.2f} x {product['annual_simple_rate']} x {days} / {product['day_count_basis']} = {interest/100:.2f} (ROUND_HALF_UP to cent)",
        "credit_eligibility": "not_assessed",
    }}


# ---------------------------------------------------------------- projection

def project(inputs: BusinessInputs, events: list[LedgerEvent], *, horizon_end: date | None = None,
            extend_horizon: bool = True) -> dict:
    """End-of-day projection from opening date through the horizon (inclusive)."""
    issues: list[dict] = []
    horizon = horizon_end or inputs.horizon_end
    assumptions = [
        "Daily closing cash = prior closing + inflows - outflows; end-of-day netting does not prove intraday liquidity.",
        "Amounts are synthetic tax-inclusive cash amounts; no VAT recovery or other tax event is modeled.",
        "Future receipts are projections, not guaranteed; they are never spendable in the sandbox until settled.",
    ]
    settled_by_event: dict[str, list[Settlement]] = {}
    for s in inputs.settlements:
        settled_by_event.setdefault(s.event_id, []).append(s)

    entries: list[dict] = []  # (date, signed amount, ref)
    for e in events:
        if e.currency != SUPPORTED_CURRENCY:
            raise EngineError("VALIDATION_ERROR", f"event {e.event_id}: unsupported currency {e.currency}; only CNY is supported, no conversion is performed")
        missing = [f for f, v in (("date", e.date), ("amount", e.amount_minor)) if v is None]
        if missing:
            issues.append({"code": "MISSING_EVIDENCE", "severity": "critical", "event_id": e.event_id,
                           "fields": missing, "message": f"{e.event_id} is missing {', '.join(missing)}; the decision cannot be completed until it is corrected."})
            continue
        if e.date < inputs.opening_date:
            issues.append({"code": "VALIDATION_ERROR", "severity": "critical", "event_id": e.event_id, "fields": ["date"],
                           "message": f"{e.event_id} is dated before the opening date {inputs.opening_date}; opening cash already reflects past events."})
            continue
        sign = 1 if e.direction == "in" else -1
        settlements = settled_by_event.get(e.event_id, [])
        settled = sum(s.amount_minor for s in settlements)
        outstanding = e.amount_minor - settled
        if outstanding < 0:
            issues.append({"code": "VALIDATION_ERROR", "severity": "critical", "event_id": e.event_id, "fields": ["amount"],
                           "message": f"{e.event_id} is over-settled by {-outstanding/100:.2f}."})
            outstanding = 0
        for s in settlements:
            entries.append({"date": s.actual_date, "amount": sign * s.amount_minor, "ref": e.event_id, "kind": "settled", "settlement_id": s.settlement_id})
        if outstanding:
            entries.append({"date": e.date, "amount": sign * outstanding, "ref": e.event_id, "kind": "scheduled"})

    last = max([x["date"] for x in entries], default=horizon)
    horizon_note = None
    if last > horizon:
        if not extend_horizon:
            raise EngineError("VALIDATION_ERROR", f"requested horizon {horizon} hides modeled obligations through {last}; extend the horizon")
        horizon_note = f"Horizon extended from {horizon} to {last} to include all modeled obligations."
        horizon = last
    by_day: dict[date, list[dict]] = {}
    for x in entries:
        by_day.setdefault(x["date"], []).append(x)

    daily: list[dict] = []
    bal = inputs.opening_cash_minor
    d = inputs.opening_date
    while d <= horizon:
        todays = by_day.get(d, [])
        inflow = sum(x["amount"] for x in todays if x["amount"] > 0)
        outflow = -sum(x["amount"] for x in todays if x["amount"] < 0)
        bal = bal + inflow - outflow
        daily.append({"day": day_index(inputs.opening_date, d), "date": d.isoformat(), "inflow_minor": inflow, "outflow_minor": outflow,
                      "closing_minor": bal, "event_refs": [x["ref"] for x in todays]})
        d += timedelta(days=1)

    low = min(daily, key=lambda r: (r["closing_minor"], r["day"]))  # ties -> earliest
    neg = next((r for r in daily if r["closing_minor"] < 0), None)
    breach = next((r for r in daily if r["closing_minor"] < inputs.buffer_minor), None)
    complete = not any(i["severity"] == "critical" for i in issues)
    return {
        "complete": complete,
        "issues": issues,
        "assumptions": assumptions + ([horizon_note] if horizon_note else []),
        "horizon_start": inputs.opening_date.isoformat(),
        "horizon_end": horizon.isoformat(),
        "daily": daily,
        "metrics": {
            "opening_cash_minor": inputs.opening_cash_minor,
            "buffer_minor": inputs.buffer_minor,
            "lowest_balance_minor": low["closing_minor"],
            "lowest_balance_date": low["date"],
            "lowest_balance_day": low["day"],
            "first_negative_date": neg["date"] if neg else None,
            "first_negative_day": neg["day"] if neg else None,
            "first_buffer_breach_date": breach["date"] if breach else None,
            "first_buffer_breach_day": breach["day"] if breach else None,
            "required_support_minor": max(0, inputs.buffer_minor - low["closing_minor"]),
            "ending_balance_minor": daily[-1]["closing_minor"],
        },
    }


def order_economics(events: list[LedgerEvent], financing: dict | None) -> dict:
    order_events = [e for e in events if e.order_id and e.amount_minor is not None]
    revenue = sum(e.amount_minor for e in order_events if e.direction == "in")
    costs = sum(e.amount_minor for e in order_events if e.direction == "out")
    fin_cost = financing["total_cost_minor"] if financing else 0
    return {
        "order_revenue_minor": revenue,
        "incremental_cost_minor": costs,
        "contribution_before_financing_minor": revenue - costs,
        "financing_cost_minor": fin_cost,
        "contribution_after_financing_minor": revenue - costs - fin_cost,
        "borrowed_principal_minor": financing["principal_minor"] if financing else 0,
        "label": "Incremental cash contribution before fixed overhead; not net business profit.",
    }


def run_scenario(inputs: BusinessInputs, scenario_id: str, scenario_defs: dict, catalogue: list[dict],
                 condition_status: dict[str, str], *, horizon_end: date | None = None, extend_horizon: bool = True) -> dict:
    built = build_scenario_ledger(inputs, scenario_id, scenario_defs, catalogue, condition_status)
    proj = project(inputs, built["events"], horizon_end=horizon_end, extend_horizon=extend_horizon)
    econ = order_economics(built["events"], built["financing"])
    unresolved = [c for c in built["conditions"] if c["status"] != "accepted"]
    if not proj["complete"]:
        terms_status = "incomplete"
    elif not built["conditions"]:
        terms_status = "no_conditions"
    elif unresolved:
        terms_status = "conditional"
    else:
        terms_status = "accepted"
    m = proj["metrics"]
    result = {
        "engine_version": ENGINE_VERSION,
        "scenario_id": scenario_id,
        "label": built["label"],
        "input_version": inputs.input_version,
        "terms_status": terms_status,
        "conditions": built["conditions"],
        "unresolved_conditions": unresolved,
        "transformations": built["transformations"],
        "financing": built["financing"],
        "economics": econ,
        **{k: v for k, v in proj.items()},
        "ledger": [_event_dict(e) for e in sorted(built["events"], key=lambda e: (e.date or date.max, e.event_id))],
    }
    if built["financing"]:
        result["metrics"]["residual_support_after_financing_minor"] = m["required_support_minor"]
    return result


def _event_dict(e: LedgerEvent) -> dict:
    d = copy.copy(e.__dict__)
    d["date"] = e.date.isoformat() if e.date else None
    return d


# ---------------------------------------------------------------- financing assessment

def assess_financing(inputs: BusinessInputs, scenario_defs: dict, catalogue: list[dict], condition_status: dict[str, str],
                     purpose: str, base_scenario: str = "current_terms") -> list[dict]:
    """Hard purpose/currency/amount/timing constraints first, then unknown eligibility."""
    base = run_scenario(inputs, base_scenario, scenario_defs, catalogue, condition_status)
    need = base["metrics"]["required_support_minor"]
    breach_date = base["metrics"]["first_buffer_breach_date"]
    out = []
    for p in catalogue:
        reasons, ok = [], True
        if p["purpose"] != purpose:
            ok = False
            reasons.append(f"Excluded by purpose: product is restricted to {p['purpose']}.")
        if p["currency"] != SUPPORTED_CURRENCY:
            ok = False
            reasons.append("Currency mismatch.")
        entry: dict[str, Any] = {"product_id": p["product_id"], "label": p["label"], "synthetic": True, "purpose": p["purpose"],
                                 "max_principal_minor": parse_amount_minor(p["max_principal_cny"]), "max_term_days": p["max_term_days"],
                                 "annual_simple_rate": p["annual_simple_rate"], "fee_minor": parse_amount_minor(p["fee_cny"]),
                                 "required_evidence": p["required_evidence"], "eligibility": p["eligibility"], "disclaimer": p["disclaimer"],
                                 "funding_need_minor": need}
        if ok and need == 0:
            reasons.append("No funding need in the base scenario.")
            ok = False
        if ok:
            max_p = parse_amount_minor(p["max_principal_cny"])
            if need > max_p:
                ok = False
                reasons.append(f"Amount: need {need/100:.2f} exceeds product maximum {max_p/100:.2f}.")
            if need < parse_amount_minor(p["min_principal_cny"]):
                ok = False
                reasons.append("Amount below product minimum.")
            draw = date.fromisoformat(breach_date)
            latest_repay = draw + timedelta(days=p["max_term_days"])
            repay = min(latest_repay, inputs.horizon_end)
            sim = loan_cash_events(p, need, draw, repay)
            sim_proj = project(inputs, [e for e in _scenario_events(inputs, base_scenario, scenario_defs, catalogue, condition_status)] + sim["events"])
            entry["simulated_draw_date"] = draw.isoformat()
            entry["simulated_repayment_date"] = repay.isoformat()
            entry["simulated_lowest_balance_minor"] = sim_proj["metrics"]["lowest_balance_minor"]
            entry["simulated_total_cost_minor"] = sim["summary"]["total_cost_minor"]
            if sim_proj["metrics"]["lowest_balance_minor"] < inputs.buffer_minor:
                ok = False
                reasons.append(f"Timing: repayment by {repay} (max term {p['max_term_days']} days) falls before the buffer is restored; "
                               f"simulated lowest balance {sim_proj['metrics']['lowest_balance_minor']/100:.2f}.")
        entry["passes_hard_constraints"] = ok
        entry["reasons"] = reasons or ["Purpose, currency, amount and repayment timing constraints pass in simulation."]
        entry["credit_approval"] = "not_assessed"
        out.append(entry)
    return out


def _scenario_events(inputs, scenario_id, scenario_defs, catalogue, condition_status):
    return build_scenario_ledger(inputs, scenario_id, scenario_defs, catalogue, condition_status)["events"]


def with_settlements(inputs: BusinessInputs, settlements: list[Settlement]) -> BusinessInputs:
    return replace(inputs, settlements=list(settlements))
