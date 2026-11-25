# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the containers endpoints. Private to this module."""

from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, model_validator

from app.core.ids import EntityId
from app.modules.containers._views import ContainerCount

type Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class ExchangeCreate(BaseModel):
    """Containers handed over in one visit, delivery or counter sale."""

    customer_id: EntityId
    delivered: list[ContainerCount] = []
    """Full containers the customer receives."""
    returned: list[ContainerCount] = []
    """Empty containers the customer hands back."""
    override_reason: Text | None = None
    """Required to accept empties of a different type than delivered."""
    note: Text | None = None

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not self.delivered and not self.returned:
            msg = "deliver or return at least one container"
            raise ValueError(msg)
        for counts in (self.delivered, self.returned):
            types = [count.container_type_id for count in counts]
            if len(set(types)) != len(types):
                msg = "list each container type once per side"
                raise ValueError(msg)
        return self

    def delivered_by_type(self) -> dict[EntityId, int]:
        """Delivered quantities keyed by container type.

        Returns:
            The quantities.
        """
        return {count.container_type_id: count.quantity for count in self.delivered}

    def returned_by_type(self) -> dict[EntityId, int]:
        """Returned quantities keyed by container type.

        Returns:
            The quantities.
        """
        return {count.container_type_id: count.quantity for count in self.returned}
