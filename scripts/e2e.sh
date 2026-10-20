#!/usr/bin/env bash
# Browser acceptance test: fresh database, single-process server on port 8001, Playwright, teardown.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ORDERBRIDGE_DB="$ROOT/data/e2e.sqlite3"
export ORDERBRIDGE_ALLOWED_ORIGINS="http://127.0.0.1:8001,http://localhost:8001"
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/reset_demo.py" >/dev/null
(cd "$ROOT/frontend" && npm run build >/dev/null)
(cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level warning) &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do curl -sf http://127.0.0.1:8001/api/health >/dev/null && break; sleep 0.2; done
cd "$ROOT/frontend" && OB_BASE_URL=http://127.0.0.1:8001 npx playwright test "$@"
