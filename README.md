# OrderBridge: SME order-acceptance cash copilot (synthetic prototype)

Student FinTechathon prototype for **Topic E, SME Finance Copilot**. A business owner gets a new order that is profitable, but supplier and payroll payments fall due before the buyer pays. OrderBridge answers:

> **Can I accept this order without breaching my cash buffer, and which terms or funding conditions need to change?**

It reads documented cash records, computes daily cash with and without the order, compares six plans, flags missing evidence, and prepares a specific *simulated* action. The owner approves that exact action, and a server-side policy gateway checks it, executes it once in a sandbox and issues a receipt.

**Synthetic data only.** OrderBridge is a project codename, not a trademark-cleared brand, and not an official WeBank product. No real payments, credit, FX or bank partnerships exist.

## What works

- Deterministic daily cash engine in integer minor units. All six reference scenarios match the independently computed fixtures for every day.
- Six screens: Overview, Evidence, Order decision, Compare plans, Approval & action, Receipt & audit. The header always shows the synthetic label, currency, simulated date, data version and agent mode.
- CSV import with staging, validation, duplicate and conflict handling, row correction and versioned commits. Record corrections keep an edit history.
- Owner-recorded acceptance of negotiated terms. Selecting a plan never accepts terms.
- Isolated day-3 sandbox (CNY 176,000) and an immutable prepared payment of CNY 70,000. The approval is bound to the exact payload hash and expires after 10 minutes. Execution is atomic and idempotent (176,000 → 106,000). Blocked cases are shown in the UI.
- Bounded agent with 7 typed tools, in two modes:
  - **Rule-based replay** (labelled, deterministic).
  - **Live Anthropic tool-use adapter**. The code is complete, but it has **not been run against the real API** because no key was available (see `docs/test-report.md`).
- Server-side sessions, CSRF and Origin checks, two tenants, owner and viewer roles, and evidence export (ZIP/JSON/CSV).

## Prerequisites

Verified with Python 3.13.16, Node 22.22.0 and npm 10.9.4 on Linux. Python ≥ 3.11 and Node ≥ 18 should work but were not tested.

See `RUN_LOCALLY.md` for a beginner, step-by-step guide (Windows, macOS and Linux).

## Setup

```bash
# backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock
# frontend
cd frontend && npm ci && npm run build && cd ..
# configuration (optional; app runs without it in replay mode)
cp .env.example .env    # then edit locally; .env is git-ignored
# database with seeded synthetic tenants/users
backend/.venv/bin/python scripts/reset_demo.py
```

## Run

**Single process (demo):** `scripts/start.sh` serves the API and the built frontend at <http://127.0.0.1:8000>.

**Two terminals (development):**
```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000   # terminal 1
cd frontend && npm run dev                                          # terminal 2 → http://localhost:5173 (proxies /api)
```

Sign in as `owner@demo-gba` (owner), `viewer@demo-gba` (read-only) or `owner@demo-other` (second tenant). The password is the value of `ORDERBRIDGE_DEMO_PASSWORD`, which defaults to `orderbridge-demo` when unset. These are local demo accounts only.

## Test

```bash
python3 scripts/verify_reference.py          # independent reference verifier (no app imports)
cd backend && .venv/bin/pytest -q            # 59 engine, service, API, security and agent tests
cd frontend && npx tsc -b                    # typecheck
scripts/e2e.sh                               # Playwright browser journey on a fresh DB, port 8001
```
`scripts/e2e.sh` uses the Chromium at `/opt/pw-browsers/chromium`. On another machine, set `OB_CHROMIUM` or run `npx playwright install chromium`.

## Reset

`backend/.venv/bin/python scripts/reset_demo.py [--load-example]` recreates the local database from fixtures. This erases the local audit history. Reset is deliberately **not** an HTTP route and **not** an agent tool.

## Live agent configuration

Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`, default `claude-opus-5-5`) in `.env` on the server, restart, then use **Switch to live AI** in the header. Without a key, live mode shows **Live AI unavailable**. It never silently substitutes replay.

The adapter sends the beta server-side refusal fallback (`ANTHROPIC_FALLBACKS=default`). Set it to `off` if your account rejects it.

## Layout

```
backend/app/domain    pure engine, money, CSV validation (no HTTP/DB/SDK)
backend/app/services  auth, workspace/imports, analysis, actions/policy, export
backend/app/agent     tool definitions + validation, orchestrator (replay + live)
backend/app/main.py   FastAPI routes
backend/tests         pytest suites
frontend/src          React + TypeScript screens, step chart
fixtures/             synthetic reference case, expected results, import samples
scripts/              verifier, reset, start, e2e
docs/                 design, security, tests, demo, limitations, submission, pitch
```
