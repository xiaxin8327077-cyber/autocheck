from decimal import Decimal

from auto_check.engine.money import amounts_equal, to_decimal


def test_to_decimal_preserves_exact_decimal_values():
    assert to_decimal("123.4500") == Decimal("123.4500")
    assert to_decimal(Decimal("7.10")) == Decimal("7.10")
    assert to_decimal(None) == Decimal("0")


def test_amounts_equal_requires_exact_equality():
    assert amounts_equal(Decimal("1.00"), Decimal("1.00"))
    assert not amounts_equal(Decimal("1.00"), Decimal("1.0001"))
