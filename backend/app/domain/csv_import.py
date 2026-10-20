"""Validation of the supported P0 cash_events.csv format (pure; no database)."""
from __future__ import annotations

import csv
import io
from datetime import date

from .money import SUPPORTED_CURRENCY, MoneyError, parse_amount_minor

COLUMNS = ["event_id", "date", "direction", "amount_cny", "currency", "category", "counterparty_id",
           "source_document_id", "source_ref", "confirmation_status", "description"]
CONFIRMATION_STATUSES = {"assumed", "parsed_unconfirmed", "user_confirmed", "missing", "synthetic"}
MAX_BYTES = 5 * 1024 * 1024  # local project policy, not a platform guarantee
MAX_ROWS = 10_000
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ImportRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_row(raw: dict[str, str]) -> tuple[dict, list[dict]]:
    """Return (normalized, issues). Missing date/amount stay None, never zero."""
    issues: list[dict] = []
    n: dict = {k: (raw.get(k) or "").strip() for k in COLUMNS}

    def issue(fld: str, msg: str, severity: str = "error"):
        issues.append({"field": fld, "message": msg, "severity": severity})

    if not n["event_id"]:
        issue("event_id", "event_id is required")
    if n["date"]:
        try:
            n["date"] = date.fromisoformat(n["date"]).isoformat()
        except ValueError:
            issue("date", f"'{raw.get('date')}' is not a valid YYYY-MM-DD date")
            n["date"] = None
    else:
        n["date"] = None
        issue("date", "date is missing; the record will block a complete decision", "missing")
    if n["direction"] not in ("in", "out"):
        issue("direction", "direction must be 'in' or 'out'")
    if n["currency"] != SUPPORTED_CURRENCY:
        issue("currency", f"unsupported currency '{n['currency']}'; only CNY is supported and no conversion is performed")
    amt = n.pop("amount_cny")
    if amt == "":
        n["amount_minor"] = None
        issue("amount_cny", "amount is missing; the record will block a complete decision", "missing")
    else:
        try:
            n["amount_minor"] = parse_amount_minor(amt)
        except MoneyError as exc:
            n["amount_minor"] = None
            issue("amount_cny", str(exc))
    if n["confirmation_status"] not in CONFIRMATION_STATUSES:
        issue("confirmation_status", f"confirmation_status must be one of {sorted(CONFIRMATION_STATUSES)}")
    if not n["source_document_id"]:
        issue("source_document_id", "source_document_id is required for provenance")
    if n["date"] is None or n.get("amount_minor") is None:
        n["confirmation_status"] = "missing" if not any(i["severity"] == "error" for i in issues) else n["confirmation_status"]
    return n, issues


def parse_csv(data: bytes, filename: str) -> list[dict]:
    if not filename.lower().endswith(".csv"):
        raise ImportRejected("VALIDATION_ERROR", "only .csv files are supported")
    if len(data) > MAX_BYTES:
        raise ImportRejected("VALIDATION_ERROR", "file exceeds the 5 MiB local upload limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportRejected("VALIDATION_ERROR", "file is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    if header != COLUMNS:
        missing = [c for c in COLUMNS if c not in header]
        extra = [c for c in header if c not in COLUMNS]
        raise ImportRejected("VALIDATION_ERROR", f"columns must be exactly {COLUMNS}; missing={missing} unexpected={extra}")
    rows = []
    for i, raw in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            raise ImportRejected("VALIDATION_ERROR", "file exceeds the 10000-row local limit")
        original = {k: raw.get(k) for k in COLUMNS}
        normalized, issues = normalize_row(raw)
        if not normalized["source_ref"]:
            normalized["source_ref"] = f"{filename}#row{i}"
        rows.append({"row_number": i, "original": original, "normalized": normalized, "issues": issues})
    seen: dict[str, int] = {}
    for r in rows:
        eid = r["normalized"]["event_id"]
        if eid and eid in seen:
            r["issues"].append({"field": "event_id", "message": f"duplicate event_id within file (also row {seen[eid]})", "severity": "error"})
        seen.setdefault(eid, r["row_number"])
    return rows


ECONOMIC_FIELDS = ("date", "direction", "amount_minor", "currency", "counterparty_id", "category")


def compare_with_existing(normalized: dict, existing: dict | None) -> str:
    """new | identical (idempotent no-op) | conflict (requires review)."""
    if existing is None:
        return "new"
    same = all(normalized.get(f) == existing.get(f) for f in ECONOMIC_FIELDS)
    return "identical" if same else "conflict"


def escape_csv_text(value) -> str:
    """Neutralise spreadsheet formula injection in exported text fields."""
    if value is None:
        return ""
    s = str(value)
    return "'" + s if s.startswith(FORMULA_PREFIXES) else s
