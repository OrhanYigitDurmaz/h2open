# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Money."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.money import CurrencyMismatchError, Money


def try_(amount: str) -> Money:
    """Build an amount in TRY from a string.

    Returns:
        The amount as Money.
    """
    return Money(amount=Decimal(amount), currency="TRY")


def test_zero() -> None:
    """Zero has amount 0 in the requested currency."""
    assert Money.zero("EUR") == Money(amount=Decimal(0), currency="EUR")


def test_add_and_subtract_are_exact() -> None:
    """Decimal arithmetic avoids float rounding errors."""
    assert try_("0.1") + try_("0.2") == try_("0.3")
    assert try_("1.00") - try_("0.30") == try_("0.70")


def test_multiply_by_quantity() -> None:
    """A unit price times a quantity keeps full precision."""
    assert try_("12.345") * 3 == try_("37.035")
    assert try_("10") * Decimal("0.2") == try_("2.0")


def test_rounded_half_up() -> None:
    """Rounding goes half up to the requested places."""
    assert try_("2.345").rounded() == try_("2.35")
    assert try_("2.344").rounded() == try_("2.34")
    assert try_("2.5").rounded(0) == try_("3")


def test_mixing_currencies_is_rejected() -> None:
    """Adding or subtracting different currencies raises."""
    eur = Money(amount=Decimal(1), currency="EUR")
    with pytest.raises(CurrencyMismatchError, match="cannot combine TRY with EUR"):
        _ = try_("1") + eur
    with pytest.raises(CurrencyMismatchError):
        _ = try_("1") - eur


def test_is_immutable() -> None:
    """Money cannot be changed after creation."""
    money = try_("1")
    with pytest.raises(ValidationError):
        money.amount = Decimal(2)


@pytest.mark.parametrize("currency", ["try", "TL", "TRYY", ""])
def test_invalid_currency_is_rejected(currency: str) -> None:
    """Currency must be a three-letter upper-case code."""
    with pytest.raises(ValidationError):
        _ = Money(amount=Decimal(1), currency=currency)


def test_non_finite_amount_is_rejected() -> None:
    """NaN and infinity are not money."""
    with pytest.raises(ValidationError):
        _ = Money(amount=Decimal("NaN"), currency="TRY")
