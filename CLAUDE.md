# OrderBridge (FinTechathon Topic E prototype)

- Spec: `BUILD_SPEC.md` (authoritative). Status and next steps: `BUILD_STATUS.md`. Design: `docs/technical-design.md`.
- Fixtures (synthetic only): `fixtures/`. Regenerate/verify reference results: `python3 scripts/verify_reference.py [--write]`.
- Backend tests: `cd backend && .venv/bin/pytest -q`. Browser tests: `scripts/e2e.sh`. Typecheck: `cd frontend && npx tsc -b`.
- Run demo: `scripts/reset_demo.py` then `scripts/start.sh` → http://127.0.0.1:8000
- Rules: money is integer minor units (Decimal parsing, no floats); domain code in `backend/app/domain` stays free of HTTP/DB/SDK imports;
  every query is tenant-scoped from the server session; approval is never a model tool; no secrets in frontend, fixtures, logs or git.
