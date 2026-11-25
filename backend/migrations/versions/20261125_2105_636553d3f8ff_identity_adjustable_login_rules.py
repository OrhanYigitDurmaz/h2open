# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""identity: adjustable login rules.

Revision ID: 636553d3f8ff
Revises: e34c3237352b
Create Date: 2026-11-25 21:05:06.674233+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "636553d3f8ff"
down_revision: str | Sequence[str] | None = "e34c3237352b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    _ = op.create_table(
        "security_settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("session_lifetime_days", sa.Integer(), nullable=False),
        sa.Column("max_failed_logins", sa.Integer(), nullable=False),
        sa.Column("lockout_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_security_settings_single_row")),
        sa.CheckConstraint(
            "lockout_minutes BETWEEN 1 AND 1440",
            name=op.f("ck_security_settings_lockout_range"),
        ),
        sa.CheckConstraint(
            "max_failed_logins BETWEEN 3 AND 20",
            name=op.f("ck_security_settings_max_failed_range"),
        ),
        sa.CheckConstraint(
            "session_lifetime_days BETWEEN 1 AND 365",
            name=op.f("ck_security_settings_session_lifetime_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_settings")),
        schema="identity",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("security_settings", schema="identity")
