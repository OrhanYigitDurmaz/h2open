# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""company: walk-in settings.

Revision ID: 1aa43d0b657a
Revises: f6f4c58f1c0e
Create Date: 2026-11-25 20:40:18.221297+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "1aa43d0b657a"
down_revision: str | Sequence[str] | None = "f6f4c58f1c0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.add_column(
        "settings",
        sa.Column(
            "walk_in_sales_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        schema="company",
    )
    op.add_column(
        "settings",
        sa.Column(
            "walk_in_deposits_allowed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="company",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_column("settings", "walk_in_deposits_allowed", schema="company")
    op.drop_column("settings", "walk_in_sales_enabled", schema="company")
