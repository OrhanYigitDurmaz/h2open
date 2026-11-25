# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""company: settings.

Revision ID: db80f44045ca
Revises: 034df125e653
Create Date: 2026-11-25 20:20:19.363135+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "db80f44045ca"
down_revision: str | Sequence[str] | None = "034df125e653"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA company")
    _ = op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "deposit_refund_policy",
            sa.Enum(
                "PAID_AMOUNT",
                "CURRENT_PRICE",
                "NONE",
                name="deposit_refund_policy",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="company",
            ),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_settings_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        schema="company",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("settings", schema="company")
    op.execute("DROP SCHEMA company")
