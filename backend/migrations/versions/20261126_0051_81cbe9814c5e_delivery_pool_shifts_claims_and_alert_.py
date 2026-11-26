# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""delivery pool: shifts, claims and alert settings.

Revision ID: 81cbe9814c5e
Revises: 2ec45d6b2654
Create Date: 2026-11-26 00:51:29.629163+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "81cbe9814c5e"
down_revision: str | Sequence[str] | None = "2ec45d6b2654"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    _ = op.create_table(
        "claim_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "CLAIMED",
                "RELEASED",
                "TAKEN_BACK",
                name="claim_action",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="orders",
            ),
            nullable=False,
        ),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.orders.id"],
            name=op.f("fk_claim_events_order_id_orders"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim_events")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_claim_events_order_id"),
        "claim_events",
        ["order_id"],
        unique=False,
        schema="orders",
    )
    op.add_column(
        "settings",
        sa.Column(
            "unclaimed_alert_minutes",
            sa.Integer(),
            server_default=sa.text("15"),
            nullable=False,
        ),
        schema="company",
    )
    op.add_column(
        "settings",
        sa.Column(
            "uncompleted_alert_minutes",
            sa.Integer(),
            server_default=sa.text("120"),
            nullable=False,
        ),
        schema="company",
    )
    op.add_column(
        "users",
        sa.Column(
            "on_shift", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        schema="identity",
    )
    op.add_column(
        "orders", sa.Column("claimed_by", sa.Uuid(), nullable=True), schema="orders"
    )
    op.add_column(
        "orders",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        schema="orders",
    )
    op.add_column(
        "orders",
        sa.Column("pooled_at", sa.DateTime(timezone=True), nullable=True),
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_orders_claimed_by"),
        "orders",
        ["claimed_by"],
        unique=False,
        schema="orders",
    )
    # Open deliveries taken before this migration wait in the pool.
    orders = sa.table(
        "orders",
        sa.column("status"),
        sa.column("fulfilment"),
        sa.column("created_at"),
        sa.column("pooled_at"),
        schema="orders",
    )
    op.execute(
        orders.update()
        .where(orders.c.status == "OPEN", orders.c.fulfilment == "DELIVERY")
        .values(pooled_at=orders.c.created_at)
    )
    op.create_check_constraint(
        op.f("ck_orders_only_deliveries_are_claimed"),
        "orders",
        "fulfilment = 'DELIVERY' OR (claimed_by IS NULL AND pooled_at IS NULL)",
        schema="orders",
    )
    op.create_check_constraint(
        op.f("ck_settings_unclaimed_alert_range"),
        "settings",
        "unclaimed_alert_minutes BETWEEN 1 AND 1440",
        schema="company",
    )
    op.create_check_constraint(
        op.f("ck_settings_uncompleted_alert_range"),
        "settings",
        "uncompleted_alert_minutes BETWEEN 1 AND 1440",
        schema="company",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_constraint(
        op.f("ck_settings_uncompleted_alert_range"), "settings", schema="company"
    )
    op.drop_constraint(
        op.f("ck_settings_unclaimed_alert_range"), "settings", schema="company"
    )
    op.drop_constraint(
        op.f("ck_orders_only_deliveries_are_claimed"), "orders", schema="orders"
    )
    op.drop_index(
        op.f("ix_orders_orders_claimed_by"), table_name="orders", schema="orders"
    )
    op.drop_column("orders", "pooled_at", schema="orders")
    op.drop_column("orders", "claimed_at", schema="orders")
    op.drop_column("orders", "claimed_by", schema="orders")
    op.drop_column("users", "on_shift", schema="identity")
    op.drop_column("settings", "uncompleted_alert_minutes", schema="company")
    op.drop_column("settings", "unclaimed_alert_minutes", schema="company")
    op.drop_index(
        op.f("ix_orders_claim_events_order_id"),
        table_name="claim_events",
        schema="orders",
    )
    op.drop_table("claim_events", schema="orders")
