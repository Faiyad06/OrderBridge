"""Read the synthetic fixtures shipped in /fixtures."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from .config import FIXTURES_DIR
from .domain.csv_import import parse_csv
from .domain.engine import BusinessInputs, LedgerEvent
from .domain.money import parse_amount_minor


def read_json(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())


@lru_cache
def scenario_defs() -> dict:
    return read_json("scenarios.json")


@lru_cache
def catalogue() -> list[dict]:
    return read_json("financing_catalogue.json")


def fixture_rows(name: str) -> list[dict]:
    path: Path = FIXTURES_DIR / name
    return parse_csv(path.read_bytes(), path.name)


def event_from_normalized(n: dict, order_id: str | None = None) -> LedgerEvent:
    return LedgerEvent(
        event_id=n["event_id"], date=date.fromisoformat(n["date"]) if n["date"] else None, direction=n["direction"],
        amount_minor=n["amount_minor"], currency=n["currency"], category=n["category"], counterparty_id=n["counterparty_id"] or None,
        source_document_id=n["source_document_id"], source_ref=n["source_ref"], confirmation_status=n["confirmation_status"],
        order_id=order_id,
    )


def reference_inputs() -> BusinessInputs:
    """Reference case built straight from fixtures (used by engine tests)."""
    b = read_json("business.json")
    events = [event_from_normalized(r["normalized"]) for r in fixture_rows("cash_events.csv")]
    events += [event_from_normalized(r["normalized"], b["order"]["order_id"]) for r in fixture_rows("order_ORDER-001.csv")]
    return BusinessInputs(
        business_id=b["business_id"], opening_date=date.fromisoformat(b["opening_date"]),
        opening_cash_minor=parse_amount_minor(b["opening_cash_cny"]), buffer_minor=parse_amount_minor(b["owner_buffer_cny"]),
        horizon_end=date.fromisoformat(b["horizon_end"]), input_version=1, events=events,
    )
