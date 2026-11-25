# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exchange planning: pure rules, no database. Private to this module.

An exchange is what happens at the door or the counter: the customer gets
full containers and hands back empties. Per container type:

1. Full given for an empty of the same type is a *swap*: nothing changes.
2. Extra fulls are *issued*: the customer pays a deposit for each.
3. Extra empties are *returned*: the deposit is refunded per company policy.

If the customer receives extra fulls of one type while returning extra
empties of another type (Brand A water, Brand B carboy back), that is a
*mismatch*. Staff may override it: the empty is accepted in place of the
full and its deposit is *transferred* to the new type, so no money moves.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.containers._views import MovementKind

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.core.ids import EntityId


@dataclass(frozen=True, slots=True)
class Step:
    """One thing to record.

    For ``TRANSFER_OUT``, ``container_type_id`` is the type handed back and
    ``to_container_type_id`` the type received in its place.
    """

    kind: MovementKind | None
    """``None`` for a swap, which is reported but not recorded."""
    container_type_id: EntityId
    quantity: int
    to_container_type_id: EntityId | None = None

    @property
    def target(self) -> EntityId:
        """The type the customer ends up holding: the received one for transfers.

        Returns:
            The container type ID.
        """
        return self.to_container_type_id or self.container_type_id


@dataclass(frozen=True, slots=True)
class Plan:
    """The steps of one exchange, in order."""

    steps: tuple[Step, ...]
    mismatched: bool
    """True when types were substituted; needs a staff override."""


def plan_exchange(
    delivered: Mapping[EntityId, int], returned: Mapping[EntityId, int]
) -> Plan:
    """Work out what an exchange means for the customer's balances.

    Args:
        delivered: Full containers the customer receives, by type.
        returned: Empty containers the customer hands back, by type.

    Returns:
        Swaps first, then transfers (if mismatched), issues and returns.
    """
    steps: list[Step] = []
    extra_out: dict[EntityId, int] = {}
    extra_in: dict[EntityId, int] = {}
    for type_id in sorted(delivered.keys() | returned.keys()):
        out, back = delivered.get(type_id, 0), returned.get(type_id, 0)
        swapped = min(out, back)
        if swapped:
            steps.append(Step(None, type_id, swapped))
        if out > swapped:
            extra_out[type_id] = out - swapped
        if back > swapped:
            extra_in[type_id] = back - swapped

    mismatched = bool(extra_out and extra_in)
    if mismatched:
        steps.extend(_transfers(extra_out, extra_in))
    steps.extend(Step(MovementKind.ISSUE, t, q) for t, q in extra_out.items() if q)
    steps.extend(Step(MovementKind.RETURN, t, q) for t, q in extra_in.items() if q)
    return Plan(tuple(steps), mismatched)


def _transfers(
    extra_out: dict[EntityId, int], extra_in: dict[EntityId, int]
) -> list[Step]:
    """Pair extra empties with extra fulls, consuming both counts.

    Returns:
        One transfer step per pairing.
    """
    steps: list[Step] = []
    for to_type in sorted(extra_out):
        for from_type in sorted(extra_in):
            quantity = min(extra_out[to_type], extra_in[from_type])
            if quantity:
                steps.append(
                    Step(MovementKind.TRANSFER_OUT, from_type, quantity, to_type)
                )
                extra_out[to_type] -= quantity
                extra_in[from_type] -= quantity
    return steps
