# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Money as an exact decimal amount in a single currency.

Never use ``float`` for money: ``0.1 + 0.2 != 0.3``. Amounts keep full
precision through arithmetic (unit prices can have more than two decimals)
and are rounded explicitly with :meth:`Money.rounded` where a document needs
a final figure.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, ConfigDict, StringConstraints

type CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
"""An ISO 4217 currency code, such as ``TRY`` or ``EUR``."""


class CurrencyMismatchError(ValueError):
    """Raised when combining amounts in different currencies."""

    def __init__(self, left: str, right: str) -> None:
        """Build the error message.

        Args:
            left: Currency of the left operand.
            right: Currency of the right operand.
        """
        super().__init__(f"cannot combine {left} with {right}")


class Money(BaseModel):
    """An immutable amount of money in one currency."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    amount: Decimal
    currency: CurrencyCode

    @classmethod
    def zero(cls, currency: CurrencyCode) -> Self:
        """Return zero in the given currency.

        Args:
            currency: The currency code.

        Returns:
            A ``Money`` with amount ``0``.
        """
        return cls(amount=Decimal(0), currency=currency)

    def __add__(self, other: Self) -> Self:
        """Add two amounts in the same currency.

        Args:
            other: The amount to add.

        Returns:
            The sum.
        """
        self._require_same_currency(other)
        return self.model_copy(update={"amount": self.amount + other.amount})

    def __sub__(self, other: Self) -> Self:
        """Subtract an amount in the same currency.

        Args:
            other: The amount to subtract.

        Returns:
            The difference.
        """
        self._require_same_currency(other)
        return self.model_copy(update={"amount": self.amount - other.amount})

    def __mul__(self, factor: Decimal | int) -> Self:
        """Multiply by a quantity or rate, for example a unit price by 12.

        Args:
            factor: The multiplier. ``float`` is deliberately not accepted.

        Returns:
            The product, unrounded.
        """
        return self.model_copy(update={"amount": self.amount * factor})

    def rounded(self, places: int = 2) -> Self:
        """Round half up to a number of decimal places.

        Args:
            places: Decimal places to keep; 2 for most currencies.

        Returns:
            The rounded amount.
        """
        exponent = Decimal(1).scaleb(-places)
        return self.model_copy(
            update={"amount": self.amount.quantize(exponent, ROUND_HALF_UP)}
        )

    def _require_same_currency(self, other: Self) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)
