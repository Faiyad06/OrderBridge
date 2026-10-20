"""Money helpers. All authoritative amounts are integer minor units (CNY 1 = 100)."""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

SUPPORTED_CURRENCY = "CNY"
_DECIMAL_RE = re.compile(r"^\d+(\.\d+)?$")


class MoneyError(ValueError):
    pass


def parse_amount_minor(text: str | None, *, allow_negative: bool = False) -> int:
    """Parse a user decimal string such as '70000.00' into minor units.

    Rejects formulas, signs (unless allowed), exponent notation and more than two
    fractional digits instead of silently rounding.
    """
    if text is None:
        raise MoneyError("amount is missing")
    s = str(text).strip()
    if s == "":
        raise MoneyError("amount is missing")
    if s[0] in "=+@" or s.startswith("-") and not allow_negative:
        raise MoneyError("amount must be a plain positive decimal, not a formula or signed value")
    body = s[1:] if allow_negative and s.startswith("-") else s
    if not _DECIMAL_RE.match(body):
        raise MoneyError(f"amount '{s}' is not a plain decimal number")
    if "." in body and len(body.split(".")[1]) > 2:
        raise MoneyError(f"amount '{s}' has more than two fractional digits")
    try:
        value = Decimal(s)
    except InvalidOperation as exc:  # pragma: no cover - regex guards this
        raise MoneyError(f"amount '{s}' is not a number") from exc
    return int(value * 100)


def format_cny(minor: int | None) -> str | None:
    if minor is None:
        return None
    sign = "-" if minor < 0 else ""
    v = abs(minor)
    return f"{sign}{v // 100}.{v % 100:02d}"


def simple_interest_minor(principal_minor: int, annual_rate: str, days: int, basis: int) -> int:
    """Simple interest, rounded once to the cent with ROUND_HALF_UP."""
    raw = Decimal(principal_minor) * Decimal(annual_rate) * Decimal(days) / Decimal(basis)
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
