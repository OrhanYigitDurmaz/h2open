# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""telephony: ring settings and call log.

Revision ID: 8073958a00c5
Revises: 387c716d5d5e
Create Date: 2026-11-26 02:25:26.441480+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "8073958a00c5"
down_revision: str | Sequence[str] | None = "387c716d5d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA telephony")
    _ = op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("line", sa.String(length=50), nullable=False),
        sa.Column("caller_number", sa.String(length=50), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "RINGING",
                "ANSWERED",
                "COMPLETED",
                "MISSED",
                name="call_status",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="telephony",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by", sa.String(length=100), nullable=True),
        sa.Column("answered_by_user", sa.Uuid(), nullable=True),
        sa.Column(
            "end_reason",
            sa.Enum(
                "CALLER_HUNG_UP",
                "ANSWERER_HUNG_UP",
                "NO_ANSWER",
                "INTERRUPTED",
                name="end_reason",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="telephony",
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calls")),
        schema="telephony",
    )
    op.create_index(
        op.f("ix_telephony_calls_caller_number"),
        "calls",
        ["caller_number"],
        unique=False,
        schema="telephony",
    )
    op.create_index(
        op.f("ix_telephony_calls_customer_id"),
        "calls",
        ["customer_id"],
        unique=False,
        schema="telephony",
    )
    op.create_index(
        op.f("ix_telephony_calls_status"),
        "calls",
        ["status"],
        unique=False,
        schema="telephony",
    )
    _ = op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "ring_strategy",
            sa.Enum(
                "SHOP_FIRST",
                "EVERYONE",
                "SHOP_ONLY",
                name="ring_strategy",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="telephony",
            ),
            nullable=False,
        ),
        sa.Column("driver_ring_delay_seconds", sa.Integer(), nullable=False),
        sa.Column("ring_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "shop_endpoints", postgresql.ARRAY(sa.String(length=100)), nullable=False
        ),
        sa.Column("driver_endpoint", sa.String(length=100), nullable=False),
        sa.Column("no_answer_sound", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "driver_ring_delay_seconds BETWEEN 0 AND 300",
            name=op.f("ck_settings_driver_delay_range"),
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_settings_single_row")),
        sa.CheckConstraint(
            "ring_timeout_seconds BETWEEN 10 AND 600",
            name=op.f("ck_settings_ring_timeout_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        schema="telephony",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("settings", schema="telephony")
    op.drop_index(
        op.f("ix_telephony_calls_status"), table_name="calls", schema="telephony"
    )
    op.drop_index(
        op.f("ix_telephony_calls_customer_id"), table_name="calls", schema="telephony"
    )
    op.drop_index(
        op.f("ix_telephony_calls_caller_number"), table_name="calls", schema="telephony"
    )
    op.drop_table("calls", schema="telephony")
    op.execute("DROP SCHEMA telephony")
