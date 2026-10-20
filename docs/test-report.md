# Test report (actual results)

Run on 2026-10-18 in the build container (Linux). Environment:

- Python 3.13.16, Node 22.22.0, npm 10.9.4
- FastAPI 0.146.0, pydantic 2.14.1, anthropic SDK 1.15.0, pytest 9.1.1
- @playwright/test 1.49.1, driving the preinstalled Chromium 141.0.7390.37

## Commands and outcomes

| Command | Result |
|---|---|
| `python3 scripts/verify_reference.py` | **10/10 OK**: six scenario rows from the brief's table, plus interest 1555.07, both minimum-day checks, and contribution after loan cost 57944.93 |
| `cd backend && .venv/bin/pytest -q` | **59 passed**, 0 failed (≈8.5 s) |
| `cd frontend && npx tsc -b` | **0 errors** |
| `scripts/e2e.sh` | **3 passed**, 0 failed: full owner journey; 390 px narrow viewport with no horizontal page scroll; viewer read-only |
| Manual restart check: stop uvicorn, start it again, `GET /api/workspace` | Same state after restart: 9 records, input v5, sandbox CNY 176,000, pending action still `awaiting_approval` |

Test files: `test_engine.py` (24), `test_api_flow.py` (12), `test_actions_security.py` (18), `test_agent.py` (5).

## Acceptance criteria → evidence

| # | Criterion | Test(s) | Status |
|---|---|---|---|
| 1 | Six scenarios match expected results and every daily row | `test_scenario_metrics_match_expected_results` ×6, `test_every_daily_balance_row_matches` (282 rows) | Pass |
| 2 | Current terms: negative day 3, minimum day 10, −90000, support 110000 | `test_current_terms_shortfall`; e2e metric cards | Pass |
| 3 | Deposit reduces final receipt; deferral preserves liability | `test_deposit_replaces_final_receipt_and_deferral_keeps_liability` | Pass |
| 4 | Combined terms: minimum 46000, ending 240000, conditional until accepted | `test_combined_terms_conditional_until_accepted`, `test_selecting_or_comparing_does_not_accept_terms_or_change_cash` | Pass |
| 5 | Loan interest 1555.07, total cost 2055.07, ending 237944.93 | `test_loan_costs` | Pass |
| 6 | Missing receipt date → needs_information, no action | `test_missing_receipt_date_is_incomplete_not_zero`, `test_missing_receipt_date_needs_information_and_blocks_action` | Pass |
| 7 | Exact duplicate is a no-op; conflict needs review | `test_import_exact_duplicate_creates_no_event`, `test_import_conflicting_duplicate_requires_review`, `test_same_amount_distinct_ids_are_not_duplicates` | Pass |
| 8 | 10000 obligation with 4000 settlement leaves 6000 outstanding; total 10000 | `test_partial_settlement_counts_obligation_once` | Pass |
| 9 | No order or invoice receipt counted twice | `test_settled_events_not_counted_twice`; forecast after the sandbox payment in `test_approved_execution_settles_once_and_is_idempotent`; reload of the example in `test_load_example_compare_and_decision` | Pass |
| 10 | Horizon excluding day-46 obligations is extended or rejected | `test_horizon_excluding_obligations_rejected_or_extended`, `test_horizon_rejection_explicit` | Pass |
| 11 | Unapproved 70000 execution rejected | `test_unapproved_execution_rejected`; e2e | Pass |
| 12 | Approved execution goes 176000 → 106000 and settles once | `test_approved_execution_settles_once_and_is_idempotent`; e2e | Pass |
| 13 | Repeat with the same key returns the original receipt | same test | Pass |
| 14 | Simultaneous identical executions → one effect | `test_concurrent_identical_execution_single_effect` (8 threads, separate SQLite connections) | Pass |
| 15 | Key reused for a different payload → conflict | `test_idempotency_key_reuse_with_different_payload_conflicts` | Pass |
| 16 | Amount, recipient, input, account or policy change → stale approval | `test_stale_approval_amount_or_recipient_tampering`, `test_stale_approval_input_change`, `test_stale_approval_account_and_policy_change`, `test_approval_rejects_mismatched_reviewed_hash` | Pass |
| 17 | Approval expiry with an injected clock | `test_approval_expires_with_injected_clock` | Pass |
| 18 | 120000 violates the per-payment limit even with enough cash | `test_per_payment_limit_blocks_120000_even_with_cash`; e2e | Pass |
| 19 | Unknown and other-tenant recipients rejected | `test_unknown_and_other_tenant_recipients_rejected` | Pass |
| 20 | Viewer and other tenant cannot approve or execute | `test_viewer_and_other_tenant_cannot_approve_or_execute`, `test_viewer_cannot_mutate` | Pass |
| 21 | Prompt injection cannot alter recipient, limits or policy | `test_prompt_injection_cannot_change_recipient_limits_or_policy` (replay + scripted live client) | Pass (server boundary; not a real model) |
| 22 | Model outage visible; replay separately labelled | `test_live_outage_is_visible_not_silently_replayed`, `test_replay_is_labelled_and_prepares_but_never_approves` | Pass |
| 23 | Data persists across a backend restart | `test_edit_records_history_and_persists_recalculation` (connections dropped, new client); manual uvicorn restart check above | Pass |
| 24 | Export has versions, assumptions, IDs and logs, and no secrets | `test_export_contains_versions_and_no_secrets`, `test_health_has_no_secrets` | Pass |
| 25 | Complete browser flow, including reload and returning between screens | e2e `owner journey` (reloads after approval, revisits Compare and Receipt) | Pass |

## Blocked or not run

- **Live-agent acceptance gate: BLOCKED.** No `ANTHROPIC_API_KEY` was available in the build environment. The live adapter (`backend/app/agent/orchestrator.py::_live`) was tested only with a **scripted fake client** (`test_live_loop_with_fake_client_validates_facts`, plus the injection test). That covers loop mechanics, budgets and fact validation, but **no real model call was made**. Specifically unverified:
  - acceptance of the request shape (`output_config.effort`, beta `server-side-fallback-2026-07-01` with `fallbacks: "default"`);
  - real tool-choice behaviour;
  - latency.

  **To close this gate:** set the key in `.env`, restart the server, switch to live AI, ask the reference question, approve the drafted action, then click "Let the agent execute this approved action". Afterwards, check the run in the evidence export under `agent_runs`.
- **Not run:** demo video recording (steps are in `demo-script.md`), screen-reader testing, cross-browser runs (Chromium only), load and fuzz testing, dependency vulnerability scan.
- **Screenshots** from the e2e run are in `docs/screenshots/` (01–08). They were generated by the test, not composed by hand.
