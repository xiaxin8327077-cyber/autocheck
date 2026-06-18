from __future__ import annotations

from decimal import Decimal
from typing import Any


def to_decimal(value: Any) -> Decimal:
    """Convert database numeric values to Decimal without applying tolerance."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def amounts_equal(left: Decimal, right: Decimal) -> bool:
    return left == right
