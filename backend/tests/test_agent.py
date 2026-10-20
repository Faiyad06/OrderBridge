"""Agent tool loop, replay labelling, provider outage and prompt injection (criteria 21-22)."""
from types import SimpleNamespace

from app.agent import orchestrator
from app.config import FIXTURES_DIR

from .conftest import accept_combined_and_init
from .test_api_flow import upload


class Block(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if v is not None}


def tool_use(i, name, inp):
    return Block(type="tool_use", id=f"tu_{i}", name=name, input=inp)


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic; records requests. Not a live call."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.requests.append(kw)
        blocks = self.script.pop(0)
        return SimpleNamespace(id=f"msg_{len(self.requests)}", content=blocks, usage=None,
                               stop_reason="tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn")


def test_replay_is_labelled_and_prepares_but_never_approves(owner):
    accept_combined_and_init(owner)
    env = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "replay"}).json()
    assert env["execution_mode"] == "rule_based_replay" and env["mode_label"] == "Rule-based replay, no live model"
    assert env["decision_code"] == "ready_for_simulation"
    tools = [t["tool"] for t in env["tool_log"]]
    assert tools[:3] == ["get_business_summary", "list_evidence", "compare_scenarios"] and "prepare_sandbox_payment" in tools
    act = next(p for p in env["proposed_actions"] if p.get("action_id"))
    assert act["state"] == "awaiting_approval"
    # agent cannot execute without owner approval
    r = owner.post("/api/agent/tasks", json={"task": "execute_approved", "action_id": act["action_id"], "mode": "replay"})
    assert r.status_code == 409 and r.json()["code"] == "APPROVAL_REQUIRED"
    a = owner.get(f"/api/actions/{act['action_id']}").json()
    owner.post(f"/api/actions/{a['action_id']}/approve", json={"payload_hash": a["payload_hash"]})
    done = owner.post("/api/agent/tasks", json={"task": "execute_approved", "action_id": a["action_id"], "mode": "replay"}).json()
    assert done["receipt"]["balance_after_minor"] == 10_600_000 and done["tool_log"][0]["tool"] == "execute_approved_sandbox_action"


def test_replay_conditional_before_acceptance(owner):
    owner.post("/api/workspace/load-example")
    env = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "replay"}).json()
    assert env["decision_code"] == "conditional_terms" and "list_financing_options" in [t["tool"] for t in env["tool_log"]]
    assert {c["condition_id"] for c in env["unresolved_conditions"]} == {"buyer_deposit_30pct", "supplier_deferral_50pct"}
    assert not any(p.get("action_id") for p in env["proposed_actions"])


def test_live_outage_is_visible_not_silently_replayed(owner):
    owner.post("/api/workspace/load-example")
    ws = owner.get("/api/workspace").json()
    assert ws["agent"]["mode"] == "replay" and ws["agent"]["live_configured"] is False
    r = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "live"})
    assert r.status_code == 503 and r.json()["code"] == "PROVIDER_UNAVAILABLE"
    runs = owner.get("/api/export").json()["agent_runs"]
    assert runs[-1]["status"] == "provider_unavailable" and runs[-1]["mode"] == "live" and runs[-1]["envelope"] is None


def test_live_loop_with_fake_client_validates_facts(owner):
    owner.post("/api/workspace/load-example")
    holder = {}

    def factory():
        return holder["client"]

    def script_with(summary_fn):
        state = {}

        class C(FakeClient):
            def _create(self, **kw):
                if len(self.requests) == 1:  # after compare_scenarios: read run ids from the tool result
                    import json
                    res = json.loads(kw["messages"][-1]["content"][0]["content"])
                    state["rows"] = {s["scenario_id"]: s for s in res["result"]["scenarios"]}
                    self.script[0] = [tool_use(2, "submit_decision", summary_fn(state["rows"]))]
                return super()._create(**kw)
        return C([[tool_use(1, "compare_scenarios", {})], None])

    good = lambda rows: {"decision_code": "conditional_terms", "summary": "Current terms dip to CNY -90,000.00; combined terms keep cash at 46000.00 if both counterparties agree.",
                         "fact_refs": [{"run_id": rows["current_terms"]["run_id"], "metric_key": "lowest_balance_minor"},
                                       {"run_id": rows["combined_terms"]["run_id"], "metric_key": "lowest_balance_minor"}]}
    holder["client"] = script_with(good)
    orchestrator.set_client_factory(factory)
    env = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "live"}).json()
    assert env["execution_mode"] == "live_model" and "model_output_error" not in env and env["summary"].startswith("Current terms")
    assert holder["client"].requests[0]["tools"][-1]["name"] == "submit_decision"
    assert "execute_approved_sandbox_action" not in {t["name"] for t in holder["client"].requests[0]["tools"]}

    bad = lambda rows: {"decision_code": "ready_for_simulation", "summary": "You will end with CNY 999,999.00, accept unconditionally.",
                        "fact_refs": [{"run_id": "run_fake", "metric_key": "lowest_balance_minor"}]}
    holder["client"] = script_with(bad)
    env = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "live"}).json()
    assert env["decision_code"] == "conditional_terms" and env["model_output_error"]
    assert any("999,999.00" in p for p in env["model_output_error"]) and "Model output was rejected" in env["summary"]


def test_prompt_injection_cannot_change_recipient_limits_or_policy(owner):
    accept_combined_and_init(owner)
    p = upload(owner, "prompt_injection.csv").json()
    v = owner.get("/api/workspace").json()["business"]["input_version"]
    owner.post(f"/api/imports/{p['import_id']}/commit", json={"expected_version": v})
    ev = owner.get("/api/evidence/INJ-001").json()
    assert "SYSTEM OVERRIDE" in ev["description"]  # stays source text
    # replay: injected text has no effect on the prepared payload
    env = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "replay"}).json()
    act = owner.get(f"/api/actions/{next(x['action_id'] for x in env['proposed_actions'] if x.get('action_id'))}").json()
    assert act["payload"]["recipient_id"] == "SUP-MAT-001" and act["payload"]["amount_minor"] == 7_000_000
    # live (scripted to obey the injection): server blocks attacker recipient, amount, and missing tools
    client = FakeClient([
        [tool_use(1, "list_evidence", {})],
        [tool_use(2, "prepare_sandbox_payment", {"scenario_id": "combined_terms", "obligation_event_id": "ORD-001-MAT-1", "recipient_id": "ATTACKER-0001", "amount_cny": "150000.00"}),
         tool_use(3, "set_policy_limit", {"per_payment_limit": 999999}),
         tool_use(4, "execute_approved_sandbox_action", {"action_id": "act_0000000000000000"})],
        [Block(type="text", text="done")],
    ])
    orchestrator.set_client_factory(lambda: client)
    env = owner.post("/api/agent/tasks", json={"task": "analyze_order", "mode": "live"}).json()
    log = {t["tool"]: t for t in env["tool_log"]}
    assert log["prepare_sandbox_payment"]["outcome"] == "blocked"
    assert log["set_policy_limit"]["error_code"] == "POLICY_BLOCKED" and log["execute_approved_sandbox_action"]["error_code"] == "APPROVAL_REQUIRED"
    blocked = owner.get(f"/api/actions/{log['prepare_sandbox_payment']['result_ids'][0]}").json()
    failed = {c["check"] for c in blocked["policy_checks"] if not c["passed"]}
    assert {"recipient_allowlisted", "per_payment_limit"} <= failed and blocked["state"] == "blocked"
    ws = owner.get("/api/workspace").json()
    assert ws["policy"]["per_payment_limit_minor"] == 10_000_000 and ws["sandbox"]["available_minor"] == 17_600_000
    assert env["model_output_error"] == "no_decision"
