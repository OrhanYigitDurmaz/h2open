# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""identity: users, roles, sessions; record actors.

Revision ID: e34c3237352b
Revises: 16defae1b36d
Create Date: 2026-11-25 20:57:53.365983+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e34c3237352b"
down_revision: str | Sequence[str] | None = "16defae1b36d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA identity")
    _ = op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
        schema="identity",
    )
    _ = op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "platform",
            sa.Enum(
                "WEB",
                "ANDROID",
                name="platform",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="identity",
            ),
            nullable=False,
        ),
        sa.Column("client_name", sa.String(length=100), nullable=True),
        sa.Column("fcm_token", sa.String(length=4096), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity.users.id"], name=op.f("fk_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_sessions_user_id"),
        "sessions",
        ["user_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        "uq_sessions_fcm_token_live",
        "sessions",
        ["fcm_token"],
        unique=True,
        schema="identity",
        postgresql_where=sa.text("fcm_token IS NOT NULL AND revoked_at IS NULL"),
    )
    _ = op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "ADMIN",
                "STAFF",
                "DRIVER",
                name="role",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="identity",
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity.users.id"], name=op.f("fk_user_roles_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", "role", name=op.f("pk_user_roles")),
        schema="identity",
    )
    op.add_column(
        "movements",
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        schema="containers",
    )
    op.add_column(
        "orders", sa.Column("created_by", sa.Uuid(), nullable=False), schema="orders"
    )
    op.add_column(
        "orders", sa.Column("completed_by", sa.Uuid(), nullable=True), schema="orders"
    )
    op.add_column(
        "orders", sa.Column("cancelled_by", sa.Uuid(), nullable=True), schema="orders"
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_column("orders", "cancelled_by", schema="orders")
    op.drop_column("orders", "completed_by", schema="orders")
    op.drop_column("orders", "created_by", schema="orders")
    op.drop_column("movements", "recorded_by", schema="containers")
    op.drop_table("user_roles", schema="identity")
    op.drop_index(
        "uq_sessions_fcm_token_live",
        table_name="sessions",
        schema="identity",
        postgresql_where=sa.text("fcm_token IS NOT NULL AND revoked_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_identity_sessions_user_id"), table_name="sessions", schema="identity"
    )
    op.drop_table("sessions", schema="identity")
    op.drop_table("users", schema="identity")
    op.execute("DROP SCHEMA identity")
