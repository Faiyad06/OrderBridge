"""Explicit local reset: recreate the demo SQLite database from fixtures.

Not an HTTP route and not an LLM tool. Erases the local demo database, including its audit
history, so only run it when starting a fresh demonstration.

Usage: backend/.venv/bin/python scripts/reset_demo.py [--load-example]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.seed import demo_password, seed  # noqa: E402

path = seed(load_example="--load-example" in sys.argv)
print(f"Seeded synthetic demo database at {path}")
print("Accounts: owner@demo-gba (owner), viewer@demo-gba (viewer), owner@demo-other (second tenant owner)")
print("Password: value of ORDERBRIDGE_DEMO_PASSWORD" + (" (default 'orderbridge-demo')" if demo_password() == "orderbridge-demo" else ""))
