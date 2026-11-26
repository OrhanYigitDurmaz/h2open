# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""outbox events.

Revision ID: 387c716d5d5e
Revises: 81cbe9814c5e
Create Date: 2026-11-26 01:08:16.139076+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "387c716d5d5e"
down_revision: str | Sequence[str] | None = "81cbe9814c5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA outbox")
    _ = op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        schema="outbox",
    )
    op.create_index(
        "ix_events_pending",
        "events",
        ["next_attempt_at"],
        unique=False,
        schema="outbox",
        postgresql_where=sa.text("handled_at IS NULL AND failed_at IS NULL"),
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        "ix_events_pending",
        table_name="events",
        schema="outbox",
        postgresql_where=sa.text("handled_at IS NULL AND failed_at IS NULL"),
    )
    op.drop_table("events", schema="outbox")
    op.execute("DROP SCHEMA outbox")
