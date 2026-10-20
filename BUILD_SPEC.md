# OrderBridge Claude Build Brief

Prepared for Ravi on 18 October 2026. This is a specification to implement, not a claim that the application already exists. All businesses, records, rates and transactions defined here are synthetic. The financial reference results have been independently calculated for this handoff.

## 1 Your assignment

Act as the implementation engineer for OrderBridge, an English-language student FinTechathon prototype under Topic E, SME Finance Copilot. Build a complete local application, not just a plan, static dashboard or chatbot mockup. Work in the provided project folder, run the code, validate it, fix failures and produce the submission documentation. Do not deploy publicly, spend money, contact people, register the team, submit the entry or perform a real financial transaction unless Ravi separately instructs you to do that.

If your environment can edit files and run commands, implement directly. If it cannot, say that plainly and provide the project as downloadable files or complete file batches, with exact installation instructions. Do not claim that code or tests ran when they did not. Prefer Claude Code in a project folder for the implementation workflow.

Read this specification and the supplied fixture files completely. Briefly identify any actual contradictions, inspect an existing repository if present, then start coding. For ordinary implementation choices, use the defaults below and continue. Ask only when a missing credential, inaccessible dependency or a consequential ambiguity actually prevents progress. If API access is unavailable, finish the deterministic application and the clearly labelled replay mode while reporting the live-agent gate as incomplete.

Keep a concise BUILD_STATUS.md with completed work, current failing checks, decisions, file locations and next commands so another session can continue. Do not stop at each milestone to ask whether to proceed.

## 2 The idea in plain language

A business owner receives a new order. The order may have a positive contribution, but supplier payments and payroll may fall due before the buyer pays. OrderBridge answers: **Can I accept this order without breaching my chosen cash buffer, and which terms or funding conditions need to change?**

It reads documented cash obligations and receipts, calculates daily cash with and without the order, compares alternatives, points out missing evidence, and prepares a specific simulated action. The owner approves an exact action. A separate server-side policy gateway checks it, executes it in a sandbox and creates a receipt.

The differentiator to implement is the full evidence-to-decision-to-controlled-action workflow. Do not claim that cash planning itself is novel, that the product approves loans, or that internal hashes prove real-world transaction truth.

Working name: OrderBridge. This is a project codename, not a trademark-cleared brand or an official WeBank product. Use no bank logos or implied partnerships.

## 3 The one complete user journey

1. The owner signs into the local demo and selects Load synthetic example, or imports the supported CSV.
2. Evidence view shows source records, amounts, dates, whether fields are confirmed, and issues requiring correction.
3. The owner asks: Can I accept this CNY 220000 order without missing payroll?
4. The live agent calls bounded read and calculation tools. The financial engine computes the answer.
5. The interface shows the earliest shortfall, lowest balance, buffer support required, order contribution and source links.
6. Compare current terms, buyer deposit, supplier deferral, both terms, and an illustrative loan.
7. Negotiated terms are proposals until the owner explicitly records their acceptance in the synthetic case. Selecting a scenario does not accept its terms or alter account cash.
8. In the accepted combined-terms fixture, initialize the independent day-3 sandbox and prepare a CNY 70000 supplier payment.
9. Show exact recipient, amount, currency, date, cash before and after, policy checks, source versions and approval expiry.
10. The owner approves. The agent may then call the narrowly bounded execute-approved-action tool; the server revalidates and commits the simulated result once.
11. Show the receipt, audit trail and evidence export.
12. Demonstrate that changing an approved amount or source version invalidates approval, and that a prohibited request is blocked.

This journey is the acceptance target. Build it before expanding input formats or adding polish.

## 4 Scope and priorities

### P0 Required for a complete candidate

- Persistent local database and a reproducible seed/reset script.
- Server-side authenticated owner session and tenant isolation; a second tenant for access tests.
- CNY only, with no currency conversion.
- Supported UTF-8 CSV import, validation, source row references, duplicate handling and editable corrections.
- Synthetic example loading with prominent labels.
- Deterministic daily cash projection through all relevant obligations.
- Six named comparison scenarios and their conditions.
- Illustrative financing catalogue with eligibility unknowns, costs and repayment dates.
- Live model tool loop through a server adapter, plus separately labelled replay mode.
- Evidence-linked results; missing inputs remain missing.
- Exact-payload approval and server policy enforcement.
- One genuine persistent sandbox payment and a blocked action.
- Idempotency, stale-input rejection and audit export.
- Reference calculation tests, authorization tests and browser workflow checks.
- README, technical design, security self assessment, limitations, actual test report and demo guide.

### P1 Only after P0 is reliable

- One digital invoice text or PDF extraction format, with field confirmation.
- Additional partial-payment and credit-note handling beyond the provided case.
- One delayed-receipt stress scenario, explained side by side.
- Accessible keyboard interaction, layout refinement and a short video capture where tools allow it.

### Excluded from this submission build

No real payments, credit applications, loan disbursement, automatic FX trades, customer-money custody, crypto wallet, blockchain, carbon certification, warehouse cameras, tax-portal access, live tariff feeds, WeChat integration, broad legal-compliance engine, model training or multi-agent infrastructure. Do not create placeholder buttons for these features.

## 5 Technology defaults

Use these proposed defaults for a new repository. If a compatible application already exists, inspect and reuse it; do not rewrite working code merely to match a preference.

- Frontend: React, TypeScript and Vite, with simple maintained UI components or plain CSS.
- Backend: Python FastAPI and typed request validation.
- Money calculations: Python Decimal, never binary float arithmetic.
- Persistence: SQLite for the single-instance local demo, with explicit transaction boundaries and uniqueness constraints. SQLAlchemy is optional if it makes the implementation clearer.
- Chart: an accessible line or step chart showing daily balances and the owner's buffer.
- Tests: pytest for the financial and service layers; browser tests such as Playwright for the user journey if available.
- Model: an Anthropic tool-use adapter for the first live provider. Set the actual accessible model identifier in configuration; verify current official SDK/API examples rather than guessing a model name or endpoint. A later provider adapter is optional, not a P0 requirement.
- Production build: build the frontend and serve its static output with the backend, or document equivalent local hosting. For frontend development, proxy /api to the backend.

Resolve versions from current official documentation, record the actual runtimes and pin dependencies with lockfiles or equivalent. Avoid adding services that require accounts unless necessary. A local SQLite database needs a persistent file; a hosted instance with transient disk cannot be described as durable without verified persistence.

Official references checked for this handoff: https://code.claude.com/docs/en/quickstart ; https://fastapi.tiangolo.com/tutorial/ ; https://vite.dev/guide/ ; https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview ; https://docs.python.org/3/library/decimal.html . These references support the proposed tooling, not any unmeasured performance claim.

## 6 Suggested repository organization

Use frontend/, backend/app/, backend/tests/, fixtures/, docs/ and scripts/. Inside the backend separate models and schemas, import/reconciliation services, the financial engine, policy and action execution, agent adapters, auth and API routes. Keep domain arithmetic independent of HTTP and the model SDK.

Keep project-root CLAUDE.md short and point it to this specification, fixtures and test commands. Put detailed design in docs/technical-design.md. Use readable identifiers and source IDs throughout. Do not place API secrets in the frontend, fixture files, logs or source control.

## 7 Money, dates and source conventions

### Numeric representation

All persisted amounts and API money fields use integer minor units. CNY 1 = 100 minor units is the convention for this prototype. For example, CNY 70000 is 7000000 minor units. Parse user decimal strings using Decimal, reject more than two fractional places rather than silently rounding imported amounts, and convert to integer minor units. Rates are decimal strings. Round computed interest once to the cent using ROUND_HALF_UP.

The frontend may format amounts with grouping, such as CNY 70,000.00. It must not independently recompute authoritative balances with floating-point arithmetic.

### Time convention

The main reference case uses day 0 = 2026-10-01, business timezone Asia/Shanghai, and an inclusive forecast ending day 46 = 2026-11-16. All case dates are synthetic. Display Simulated date when operating the sandbox. Use UTC timestamps for approval expiry and audit timestamps, separate from the simulated business date.

The daily forecast is an end-of-day projection. Netting receipts and payments on the same date does not prove intraday liquidity; state this limitation. The action engine uses available sandbox cash at execution, never an unreceived future inflow.

### Evidence convention

Every row has a business/tenant owner, source document ID, source row reference and confirmation status. Distinguish assumed, parsed unconfirmed, user confirmed, missing and synthetic. Do not call a sample document externally verified.

For the constructed cash example, all amounts are tax-inclusive synthetic cash amounts. There is no VAT recovery or additional tax event in the reference case. The order contribution is incremental cash contribution before financing, with fixed overhead excluded; do not label it net business profit.

## 8 Exact reference case

Business ID: demo_gba_001. Fictional display name: Demo GBA Trading. Currency CNY. Opening cash CNY 100000 on day 0. Owner buffer CNY 20000.

| Day | Date | Existing business cash event |
|---|---|---|
| 1 | 2026-10-02 | Receive 60000 |
| 2 | 2026-10-03 | Pay 50000 |
| 7 | 2026-10-08 | Pay payroll 40000 |
| 14 | 2026-10-15 | Receive 80000 |
| 21 | 2026-10-22 | Pay rent 30000 |
| 30 | 2026-10-31 | Receive 60000 |

New order ORDER-001 has a buyer receipt of CNY 220000 on day 45, material cost CNY 140000 on day 3 and fulfillment cost CNY 20000 on day 10. Incremental contribution before financing is CNY 60000.

### Required scenarios

1. no_order: existing events only.
2. current_terms: add the new order unchanged.
3. buyer_deposit: receive CNY 66000, 30% of the order, on day 0 and reduce the day-45 receipt to CNY 154000.
4. supplier_deferral: pay CNY 70000 on day 3 and CNY 70000 on day 46 instead of CNY 140000 on day 3.
5. combined_terms: apply both deposit and deferral, including the reduced final buyer receipt and deferred supplier payment.
6. illustrative_loan: current terms plus CNY 110000 drawn on day 3 and repaid on day 46. Fictional simple annual interest is 12%, actual day difference 43, basis 365; fee CNY 500 paid at repayment, not deducted at draw.

| Scenario | Lowest balance CNY | First negative day | Support to keep CNY 20000 buffer | Ending balance day 46 CNY |
|---|---:|---|---:|---:|
| no_order | 70000 | None | 0 | 180000 |
| current_terms | -90000 | 3 | 110000 | 240000 |
| buyer_deposit | -24000 | 7 | 44000 | 240000 |
| supplier_deferral | -20000 | 10 | 40000 | 240000 |
| combined_terms | 46000 | None | 0 | 240000 |
| illustrative_loan | 20000 | None | 0 additional after the loan | 237944.93 |

For current_terms, the minimum first occurs on day 10. For combined_terms, it first occurs on day 10. Ties are resolved to the earliest date. For the illustrative loan, report loan draw 110000 separately from residual support 0 so users do not think no financing was needed.

Loan interest = 110000 × 0.12 × 43 / 365 = CNY 1555.07. Total interest plus fee = CNY 2055.07. Contribution after these costs = CNY 57944.93. These are fictional terms, not WeBank pricing. The fixtures include complete daily balances and minor-unit expected results.

### Conditional commercial terms

At first, deposit and deferral conditions are proposed. Show the combined plan as Conditional, even though its calculation is positive. Require separate explicit owner confirmations, labelled Mark accepted in this synthetic case, to change them to accepted. Record who confirmed what and when. Never treat selecting a comparison card or an LLM statement as counterparty acceptance.

The illustrative loan can be simulated for comparison, but actual credit eligibility remains not assessed and execution of a real borrowing action is prohibited. Never recommend unconditional order acceptance based on an unapproved loan.

## 9 Financial engine contract

For each scenario, create an event ledger, apply explicit replacements to linked events and calculate every date through the horizon. Do not simply add changed payments to the original schedule; deposit and deferral must replace the relevant original events.

Daily closing cash = prior day's closing cash + that day's inflows - that day's outflows. Include day-0 events. Required support = max(0, buffer - minimum projected closing cash). Return the lowest balance, earliest occurrence, first negative date, first buffer-breach date, ending balance, contribution, financing cost, source-event references, assumptions and unresolved conditions.

Represent a missing date or amount as null with a validation issue, not zero. A critical missing field blocks a complete numeric decision. Unsupported currencies fail with a clear message. A partial forecast may be shown only as explicitly incomplete and must not authorize an action.

The projection horizon must include all modeled debt repayments and deferred obligations. Reject a request that hides known modeled obligations beyond the requested end date, or extend the horizon and explain why.

Use event-level identifiers for reconciliation. An invoice, its import copy and its settlement are not three separate cash receipts. Maintain a linked obligation and settlements; add only outstanding scheduled amounts or actual settled amounts, once. Exact duplicate imports are idempotent. Conflicting duplicates are review issues. Identical amounts on different genuine record IDs are not automatically duplicates.

The provided main CSV is already a normalized cash schedule. Do not also derive a second copy of those six events from the evidence index. The evidence index is provenance, not another transaction source.

## 10 Import contract

Supported P0 cash_events.csv columns are event_id, date, direction, amount_cny, currency, category, counterparty_id, source_document_id, source_ref, confirmation_status and description. Direction is in or out; amount_cny is a positive decimal string, not a signed amount. The direction supplies the sign.

Validate file type, UTF-8 decoding, size, column names, dates, direction, currency, money precision, references and duplicates. Set an initial 5 MiB and 10000-row limit as local project policy, not a platform guarantee. Reject formula text in numeric fields. Escape dangerous leading spreadsheet formula characters in user-supplied text fields when exporting CSV, while keeping validated numeric fields numeric.

Stage an import for review. Show valid and invalid rows and allow correction. Do not silently commit a subset while implying the whole import succeeded. A commit creates a new input version and invalidates affected pending approvals.

Source browsing must show the original row values beside normalized values. A field edit records old value, new value, actor and timestamp. Never overwrite the only retained source representation.

## 11 Data model

Minimum records:

| Entity | Required content |
|---|---|
| User and session | server-derived user ID, role, tenant ID, password hash or chosen auth reference, session expiry |
| Business | ID, owner, name, currency, timezone, opening cash, opening date, buffer, input version |
| Source | ID, tenant, original filename or synthetic label, hash, source type, created time |
| Cash obligation or event | stable ID, currency, amount, date, direction, status, counterparty, source references |
| Settlement | unique settlement ID, linked event/obligation, actual date, amount, sandbox action ID if relevant |
| Order | receipt and incremental cost schedule with source references |
| Scenario | base version, exact transformations, proposed/accepted conditions, output run ID |
| Financing product | synthetic flag, amount and purpose constraints, cost schedule, required evidence |
| Sandbox account | tenant, currency, available balance, simulated date, ledger version |
| Action | immutable prepared payload, state, payload hash, input and account versions, idempotency key |
| Approval | owner actor, action hash, policy version, expiry, approval state |
| Audit event | actor type, action ID, tool name when applicable, timestamp, decision code, result references |

Use server-side tenant scoping in every service and query. The client or model cannot choose a different tenant by changing a request field. Add database uniqueness constraints for action idempotency and linked settlement creation. A status refresh must not repeat an economic effect.

## 12 Screens and interaction

Use a clean financial workspace: light background, dark navy text, blue primary actions, green for allowed results, amber for conditional states and red for blocked actions. Use readable tables and chart labels. Avoid decorative metrics, fake customer logos and unrelated graphics.

Persistent header: OrderBridge, Synthetic demo, base currency, simulated date when relevant, data version, and Live AI or Rule-based replay. Never hide these states in a settings screen only.

### Screen 1 Overview

Show opening cash, owner buffer, records requiring review and a prominent Analyze new order action. Include Load example, Import CSV and links to evidence. A model-status failure must not prevent access to the financial tools.

### Screen 2 Evidence

Sortable rows, import issues, source side panel, old/new values and confirmation status. Missing or conflicting critical fields block the decision and explain how to fix it. No unsupported Chinese-document claim is needed for the English MVP.

### Screen 3 Order decision

Show order revenue, incremental costs and contribution separately from cash results. Render the current-terms cash path, first shortfall, lowest balance and buffer. Every metric links to the run and contributing records. Add Why this result, showing arithmetic and payment timing, not hidden model reasoning.

### Screen 4 Compare plans

Show all six scenarios. Display terms status, lowest cash, total borrowed, finance cost, repayment date, contribution after financing and any unresolved condition. Selecting a plan does not execute it. Add owner confirmation controls for synthetic negotiated terms. Keep the no-order baseline available.

### Screen 5 Approval and action

Show immutable action preview, source and account versions, full synthetic recipient display, masked test identifier, amount, date, before/after balance and allowed/blocked reasons. Buttons name their effects. Confirming an action uses an authenticated owner route and a CSRF-protected request, not a model-provided approval flag.

### Screen 6 Receipt and audit

Show action ID, simulated status, settled amount, before/after balance, exact source links, approval details and timestamps. Provide evidence ZIP or JSON plus CSV export, action-state refresh and return to decision. Every visible button must work. Do not create a fake bank success screen.

## 13 Sandbox initialization and payment semantics

Keep the analysis ledger and actual simulated account distinguishable. A projected future receipt does not become spendable merely because it appears on a chart.

For the accepted combined-terms fixture, the sandbox starts immediately before the day-3 material payment, on 2026-10-04. CNY 100000 opening + 66000 synthetic deposit + 60000 day-1 receipt - 50000 day-2 payment = **CNY 176000 available cash**. The supplied sandbox bootstrap documents these settled inputs.

The candidate action pays **CNY 70000** to the seeded synthetic materials supplier. The receipt must show **176000 before and 106000 after**. The remaining CNY 70000 obligation stays scheduled for day 46. Link the settlement to the day-3 obligation so the forecast does not count the payment again.

Only initialize a fresh demonstration workspace or use an explicit local reset script. Reset is not an LLM tool, must not be available to an ordinary hosted user, and must not erase audit history during the main workflow. Initialization is labelled synthetic seeding, not a deposit from a real bank.

Compare/forecast endpoints are read-only. Once an action is executed, status checks, retries and returning to a screen cannot execute it again. To demonstrate a different scenario, create a new isolated sandbox rather than rewriting the settled history of the first one.

## 14 Policy and approval contract

Proposed demo limits: CNY 100000 per payment, CNY 120000 total daily outgoing, CNY 20000 minimum immediate account buffer. These are prototype policies, not legal or bank requirements. Use the seeded allowlisted materials supplier. Never let the model add a recipient or lower a limit.

Green operations are read-only queries and calculations. Yellow operations are bounded sandbox changes requiring approval. Real money, real borrowing, FX execution, cross-tenant access, arbitrary recipients and limit bypass are red and blocked.

Canonical prepared payload includes action ID, tenant, action type, recipient ID, amount_minor, currency, simulated execution date, scenario ID, financial run ID, input version, account version and policy version. Serialize deterministically and hash. Store an immutable prepared action rather than trusting the browser's repeated money fields.

Approval binds that exact payload hash to the authenticated owner and expires after 10 minutes of real elapsed time, a proposed demo policy. The model cannot call an approval tool or fabricate an owner token. A changed amount, recipient, evidence version, policy version, account version or relevant terms status requires re-preparation and re-approval.

At execution check authentication/delegation, tenant, state, expiry, exact hash, source versions, accepted conditions, recipient allowlist, amount and currency, per-action and daily limits, available cash and outstanding obligation. Recalculate the selected plan before execution and block if its required conditions or cash policy no longer hold.

Make balance deduction, daily-limit consumption, action success, settlement link and success audit record atomic. For SQLite, choose and test a transaction strategy that serializes competing account writes. Idempotency keys must be unique within the tenant and bound to the original payload. Reusing a key with a different payload returns a conflict. A repeated identical execution returns the existing receipt.

State machine: prepared -> awaiting_approval -> approved -> executing -> succeeded. Alternative terminal states are blocked, expired, cancelled and failed. Record a failure reason. A failure before a committed transaction has no economic effect. A network timeout after a potential commit is reconciled by action ID before any retry. Do not assume delivery failed because the client timed out.

Prove these controls in server tests, not only by disabling buttons.

## 15 Agent and tool contract

Implement one orchestrator with these bounded tools, using typed JSON schemas:

- get_business_summary: current version, confirmed records, unresolved issues and scope labels.
- list_evidence: tenant-scoped source records and fields.
- run_forecast: scenario ID and supported horizon, returning a stored run and authoritative metrics.
- compare_scenarios: scenario IDs and input version, returning exact calculations and conditions.
- list_financing_options: purpose and funding need, returning only the seeded catalogue and eligibility states.
- prepare_sandbox_payment: approved plan reference, seeded recipient and outstanding obligation; creates a draft payload but grants no approval.
- execute_approved_sandbox_action: action ID only, plus a server-controlled execution capability bound to the owner approval. No arbitrary amount or recipient arguments.

Approval is a separate owner UI/API operation, never a model tool. The execution gateway rechecks the database and does not trust the model's assertions that approval exists. Scope the resumed agent run to the one owner-approved action; previous approvals do not grant broad execution rights.

For each tool request validate schema, tenant context, enum values and object ownership on the server. No arbitrary shell, SQL, code execution, external URL fetching or network destination tool. Do not let document content select a tool policy.

Use the provider's current documented tool-call/result loop. Bound turns, tool calls, total request size and time. Initial proposed budgets: at most 8 model turns and 12 tool invocations per task; an exhausted budget returns a clear partial result. Configure timeouts and bounded retry only for safely repeatable operations. Never retry a payment by creating a new action identity.

Log tool names, validated argument summaries, result IDs, elapsed time, permission decisions and outcomes. Do not log hidden chain of thought, API keys or unnecessary full documents.

### Response shape

Return a typed decision envelope: decision_code, summary, fact_refs, evidence_refs, assumptions, unresolved_conditions, proposed_actions and execution_mode. Suggested decision codes are needs_information, funding_required, conditional_terms, ready_for_simulation and blocked.

Authoritative numeric cards render directly from financial result objects. A fact_ref points to a run ID and metric key. Do not accept new model-generated balances or rates as facts. Keep the model's explanation consistent with the tool output; if it invents an unsupported metric, reject that response or show a structured calculation-based explanation and flag the model-output error.

### Live versus replay

Live mode must genuinely call the configured model and retain tool-call evidence. Replay mode uses known deterministic workflow steps and labels itself Rule-based replay, no live model. The live provider failing must not silently switch the badge to a fake live experience. Allow the owner to explicitly switch to replay. A successful replay alone does not satisfy the live-agent acceptance gate.

Use an actual provider API key through server-side environment configuration. Do not extract browser cookies or repurpose a chat login as an application API credential. Provide .env.example with placeholders and a configuration guide; never ask Ravi to paste secrets into a public chat or commit them.

## 16 Financing catalogue and recommendation rules

Seed only fictional products with conspicuous Illustrative product labels. No bank name, logo, guaranteed approval or live interest-rate claim. The supplied catalogue includes:

- illustrative_working_capital: purpose working capital, principal range CNY 10000–150000, up to 60 days; the reference draw is 110000 for 43 days at fictional 12% simple annual interest and 500 fee at repayment.
- illustrative_short_bridge: maximum CNY 80000 and term 15 days, fictional 9% and CNY 200 fee; it cannot cover the reference current-terms support need and its repayment timing is too early.
- illustrative_equipment_only: purpose equipment acquisition, not general order working capital; exclude for this task by purpose.

Assess hard purpose, currency, amount and timing constraints first. Then show known and unknown eligibility evidence. Unknown credit approval remains not assessed. Compare the full cash effect of principal, fees and repayment. Existing credit approval, if later added, must have provenance and expiry.

Prefer a conditionally debt-free plan only when its terms are accepted and it satisfies the owner's chosen scenario tests. Never optimize recommendations for loan commissions. Do not guarantee the future buyer receipt.

## 17 Minimum API surface

Endpoint names below are a proposed contract; preserve semantics even if names change consistently:

| Operation | Purpose |
|---|---|
| POST /api/auth/login and logout | Create/end server session; validate role and tenant |
| GET /api/workspace | Business, versions, model mode, permitted operations |
| POST /api/imports/preview | Stage CSV and report errors without changing the ledger |
| POST /api/imports/{id}/commit | Owner commits validated staged data with expected version |
| GET /api/evidence and /api/evidence/{id} | Read scoped source records |
| PATCH /api/records/{id} | Owner correction with optimistic version check and audit |
| POST /api/forecasts | Store calculation run from validated inputs |
| POST /api/comparisons | Compare the supported scenarios |
| POST /api/scenarios/{id}/conditions | Owner records synthetic term acceptance |
| POST /api/agent/tasks | Run or resume bounded agent task |
| POST /api/actions/prepare | Create immutable sandbox action preview |
| POST /api/actions/{id}/approve | Authenticated exact-hash approval with CSRF protection |
| POST /api/actions/{id}/execute | Enforce approved execution and idempotency |
| GET /api/actions/{id} | Read status and reconcile uncertain outcomes |
| GET /api/audit and /api/export | Tenant-scoped logs and evidence bundle |
| GET /api/health | No secrets; database and model configuration status |

Use predictable error objects containing code, user_message, field_errors if relevant and request_id. Suggested codes: VALIDATION_ERROR, MISSING_EVIDENCE, VERSION_CONFLICT, APPROVAL_REQUIRED, APPROVAL_EXPIRED, POLICY_BLOCKED, RECIPIENT_NOT_ALLOWED, INSUFFICIENT_CASH, IDEMPOTENCY_CONFLICT and PROVIDER_UNAVAILABLE. Do not leak other tenants' existence through detailed errors.

## 18 Authentication and security implementation

For the local demo, implement two seeded tenants and distinct owner/viewer accounts. Derive actor, tenant and role from the server session. Store password hashes, not plaintext, and use opaque expiring sessions with HttpOnly cookies and SameSite protections. Use Secure cookies for HTTPS deployments; document local-development differences. Protect state changes against CSRF and verify Origin where applicable. No public unauthenticated reset route.

Use allowlisted file formats, upload limits, parameterized database queries and escaped output. Treat all imported descriptions and document content as untrusted data. Never evaluate formulas or render unsanitized HTML from a source or model. Mask unnecessary identifiers and keep secrets outside evidence exports.

Prove a cross-tenant record request is denied even if the caller knows the record ID. Prove a viewer cannot approve an action. Prove direct calls to the execute route without approval fail even when the UI would have disabled the button.

The synthetic prompt-injection fixture contains an instruction to ignore limits and change the payment recipient. It must remain source text. Do not claim to have solved all prompt injection; report the attacks actually tested and their outcomes.

## 19 Tests and acceptance criteria

Write meaningful tests for domain behavior and trust boundaries, not snapshots that merely repeat implementation details. At minimum:

1. All six scenarios match expected_results.json and every row of expected_daily_balances.csv.
2. Current terms have earliest negative day 3, minimum day 10, balance -90000 and support 110000.
3. Deposit reduces the final receipt; deferral preserves the future liability.
4. Combined terms produce minimum 46000 and ending 240000 but stay conditional until accepted.
5. Loan interest is 1555.07, total cost 2055.07 and ending cash 237944.93.
6. Missing receipt date produces needs_information and cannot authorize an action.
7. Exact duplicate import creates no second economic event; conflicting duplicates require review.
8. A 10000 obligation with a linked 4000 settlement leaves 6000 outstanding and total economic outflow 10000 across actual plus planned events.
9. No order or future invoice receipt is counted twice.
10. A horizon excluding day-46 obligations is extended or rejected explicitly.
11. Unapproved CNY 70000 execution is rejected.
12. Approved synthetic CNY 70000 execution changes available cash from 176000 to 106000 and settles the linked event once.
13. Repeating execution with the same key returns the original receipt and unchanged balance.
14. Simultaneous identical execution requests create one settlement and one successful economic effect.
15. Reusing a key for a different payload returns a conflict.
16. Amount, recipient, input, account or policy change after approval causes stale-approval rejection.
17. Approval expires after the configured time without sleeping in a test; inject a clock.
18. CNY 120000 violates the proposed per-payment limit even when immediate cash would cover it.
19. Unknown recipient and other-tenant recipient are rejected.
20. Viewer and other-tenant users cannot approve or execute the owner's action.
21. The prompt-injection fixture cannot alter recipient, limits or policy.
22. The model outage is visible; replay is separately labelled and never presented as a live call.
23. Data persists across a normal backend restart.
24. Evidence export contains input versions, assumptions, result IDs, action/approval logs and no secrets.
25. The complete browser flow works, including reload and returning between screens, without resetting state.

Record actual test commands, versions, pass/fail counts and any unexecuted checks. Do not fill a test report with a planned result. Live-provider checks require configured credentials; mark them blocked if unavailable, while completing the rest.

## 20 Implementation sequence

### Milestone 1 Scaffold and reference engine

Inspect repository, create package configuration, seed data, domain functions and financial tests. Run the independent fixture verifier. Show exact calculation output before styling. Gate: six scenarios match the fixture tables and money remains in minor units.

### Milestone 2 Persistent application flow

Implement imports, evidence review, versioning, authentication and the six functional screens. Wire the chart and comparison table to backend calculations. Gate: a user can change an input, reload and see the correct recalculated persisted data.

### Milestone 3 Controlled sandbox action

Implement accepted-condition state, isolated sandbox bootstrap, immutable action preparation, owner approval, policy and atomic idempotent settlement. Gate: one allowed payment, one blocked payment and stale approval all behave as specified through direct API tests.

### Milestone 4 Live agent

Implement the provider adapter and tool loop. Add structured fact references and a separately labelled replay. Gate: a live request calls tools to produce a correct decision and, after actual owner approval, invokes the approved execution path. If credentials are absent, complete integration code and report the live gate as blocked.

### Milestone 5 Adversarial and browser verification

Run the listed tests, inspect screens at desktop and narrow widths, fix failures and verify persistence. Prefer dropping P1 features over shipping broken P0 controls.

### Milestone 6 Submission preparation

Create the actual technical document, security self assessment, known-risk list, evidence export, deck outline and a four-minute demo script. If the environment can generate a playable recording, do so and verify it; otherwise provide precise recording steps and say recording is still pending. Do not claim that a video or deck file exists if only an outline exists.

The published deadline in the earlier research was 20 October 2026 at 21:59 Bangladesh time. Verify the organizer's current instructions before submission. Use a working target of 18:00 Bangladesh time that day. These are scheduling inputs, not an instruction to invent a completed registration.

## 21 Required documentation and completion report

Deliver these files after implementation:

- README with supported prerequisites, exact setup, configuration, start, test, build and reset commands; explain two-terminal development and single-process demo if both are supported.
- .env.example with placeholders only; ensure secret files are ignored.
- docs/technical-design.md with architecture, data flow, formulas, types, scenario transformations, action state machine and provider mode.
- docs/security-self-assessment.md with implemented controls, test evidence and known risks.
- docs/test-report.md with actual results and blocked or unrun checks.
- docs/demo-script.md with the exact reference case and the allowed/blocked actions.
- docs/submission-checklist.md covering registration, code link, technical/security documentation, presentation, demo and execution evidence, subject to actual organizer requirements.
- docs/limitations.md separating implemented, simulated, illustrative, unverified and deferred features.
- BUILD_STATUS.md and a short final handoff with the running app address if started, commands, credentials setup location and any remaining blockers.

The final completion report should lead with what actually works. Include exact files changed, tests run, remaining blockers, and the next manual step. No invented customers, savings percentages, partnerships, certifications, approval rates or qualification promises.

## 22 Owner launch instructions

Ravi should download the handoff ZIP, extract it into a new project folder and open Claude Code there. Paste START_PROMPT.md. If using Claude chat instead, upload this complete brief and the fixtures; request a downloadable multi-file project and actual execution where the environment supports it. Do not accept a single static HTML artifact as fulfillment of this backend and security specification.

The owner must provide a usable model API credential through local server configuration for a live in-app agent. Coding-tool access and an app's model API configuration are separate setup concerns; do not assume an available app credential. Continue replay development without a key and show that limitation.

Ravi reviews the final demo and claims, confirms team eligibility and registration documents, verifies submission requirements, records any required presentation/video that Claude cannot produce, and submits through the actual published process. Claude should prepare concrete files but should not send passports, emails or an application autonomously under this brief.

## 23 Starter instruction to Claude

Read CLAUDE.md, BUILD_SPEC.md and the fixtures. Implement OrderBridge according to this specification. Begin by inspecting the project and running the reference verifier, then build and test milestones 1 through 6 without stopping for routine confirmation. Preserve the fixed scope. Do not substitute a static UI for the financial engine, live tool integration or server-enforced approval controls. Use synthetic data only. If no model key is available, complete the app and explicit replay mode and list live verification as blocked. Keep BUILD_STATUS.md current. Finish with runnable files, actual test results, submission documentation and a precise list of remaining manual steps. Start implementation now.

## 24 Follow-up prompts when needed

### Resume after a context limit

Read CLAUDE.md, BUILD_STATUS.md, this build specification and current test failures. Inspect the repository before changing anything. Continue from the last completed milestone, preserve working behavior and fixtures, and complete the remaining acceptance criteria. Do not restart or redesign the app unnecessarily.

### If only UI was built

The interface is only part of this assignment. Implement and wire the deterministic engine, persistent data, source/version handling, actual model tool loop, authenticated exact-payload approval and atomic idempotent sandbox execution. Prove the specified 176000 to 106000 payment and blocked cases through API tests and the browser. Identify any gate still incomplete.

### Final hardening pass

Audit the implementation against every numbered acceptance criterion. Run meaningful checks. Change one amount, remove a receipt date, repeat an execution, alter an approved payload and try a cross-tenant request. Fix failures without adding new features. Update the actual test report and known risks. Prepare the final reproducible submission candidate and tell me exactly what still needs my action.
