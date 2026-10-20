# BUILD_STATUS

Last updated: 2026-10-18.

## Milestones
| # | Milestone | Status |
|---|---|---|
| 1 | Scaffold and reference engine | Done. Verifier 10/10; all six scenarios match all 282 daily rows |
| 2 | Persistent application flow | Done. SQLite, auth, imports, evidence, corrections, six screens, chart |
| 3 | Controlled sandbox action | Done. 176,000 → 106,000, blocked and stale cases proven by API tests |
| 4 | Live agent | **Code complete; live gate BLOCKED (no API key)**. Replay done; scripted fake-client tests pass |
| 5 | Adversarial and browser verification | Done. 59 pytest, 3 Playwright (desktop journey, 390 px, viewer) |
| 6 | Submission preparation | Docs done. Video and deck are pending manual work |

## Currently failing checks
None. The live-provider check has not been run (blocked).

## Decisions
- Fixtures were regenerated from the brief (the originals were not supplied). `scripts/verify_reference.py` computes them independently of the app.
- Raw `sqlite3` instead of SQLAlchemy, with `BEGIN IMMEDIATE` to serialise writes.
- The deposit, deferral and loan events are scenario terms in `fixtures/scenarios.json`, not ledger records.
- Recording a condition acceptance bumps the input version, so approvals bound to the old terms are invalidated.
- The demo password is shared across the three local accounts and set by `ORDERBRIDGE_DEMO_PASSWORD`.
- Model default: `claude-opus-5-5`, effort `medium`, optional beta server-side refusal fallback (`ANTHROPIC_FALLBACKS=off` disables it).

## Key files
- Engine: `backend/app/domain/engine.py`. Policy and execution: `backend/app/services/actions.py`. Agent: `backend/app/agent/`.
- Frontend screens: `frontend/src/screens/`. Chart: `frontend/src/CashChart.tsx`.

## Next commands
```bash
backend/.venv/bin/python scripts/reset_demo.py && scripts/start.sh   # run the demo
cd backend && .venv/bin/pytest -q && cd .. && scripts/e2e.sh          # re-verify
# close the live gate: put ANTHROPIC_API_KEY in .env, restart, Switch to live AI, Ask live agent
```

## Remaining manual steps (Ravi)
Verify the organiser rules; record the video; build the deck from `docs/pitch-deck-outline.md`; optionally run the live gate; publish the code if required; submit.
