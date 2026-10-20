#!/usr/bin/env bash
# Single-process local demo: FastAPI serves the API and the built frontend on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f data/orderbridge.sqlite3 ] || backend/.venv/bin/python scripts/reset_demo.py
cd backend && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
