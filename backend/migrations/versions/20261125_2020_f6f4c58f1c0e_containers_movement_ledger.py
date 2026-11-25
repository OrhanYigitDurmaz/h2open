# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""containers: movement ledger.

Revision ID: f6f4c58f1c0e
Revises: 0b539bf77307
Create Date: 2026-11-25 20:20:22.262411+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f6f4c58f1c0e"
down_revision: str | Sequence[str] | None = "0b539bf77307"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA containers")
    _ = op.create_table(
        "movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("container_type_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "ISSUE",
                "RETURN",
                "TRANSFER_OUT",
                "TRANSFER_IN",
                name="movement_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="containers",
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("balance_change", sa.Integer(), nullable=False),
        sa.Column("unit_deposit", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("override_reason", sa.String(length=500), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "balance_change = quantity OR balance_change = -quantity",
            name=op.f("ck_movements_balance_change_matches_quantity"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_movements_quantity_positive")),
        sa.CheckConstraint(
            "unit_deposit >= 0", name=op.f("ck_movements_unit_deposit_not_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movements")),
        schema="containers",
    )
    op.create_index(
        op.f("ix_containers_movements_customer_id"),
        "movements",
        ["customer_id"],
        unique=False,
        schema="containers",
    )
    op.create_index(
        op.f("ix_containers_movements_exchange_id"),
        "movements",
        ["exchange_id"],
        unique=False,
        schema="containers",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_containers_movements_exchange_id"),
        table_name="movements",
        schema="containers",
    )
    op.drop_index(
        op.f("ix_containers_movements_customer_id"),
        table_name="movements",
        schema="containers",
    )
    op.drop_table("movements", schema="containers")
    op.execute("DROP SCHEMA containers")
