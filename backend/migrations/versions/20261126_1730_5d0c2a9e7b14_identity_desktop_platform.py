# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""identity: desktop logins.

Revision ID: 5d0c2a9e7b14
Revises: 9abee0bec75b
Create Date: 2026-11-26 17:30:00.000000+00:00
"""

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "5d0c2a9e7b14"
down_revision: str | Sequence[str] | None = "9abee0bec75b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _allow(*platforms: str) -> None:
    """Replace the sessions.platform CHECK constraint with these members."""
    allowed = ", ".join(f"'{platform}'" for platform in platforms)
    op.drop_constraint("platform", "sessions", schema="identity")
    op.create_check_constraint(
        "platform", "sessions", f"platform IN ({allowed})", schema="identity"
    )


def upgrade() -> None:
    """Apply this migration."""
    _allow("WEB", "ANDROID", "DESKTOP")


def downgrade() -> None:
    """Revert this migration."""
    op.execute("DELETE FROM identity.sessions WHERE platform = 'DESKTOP'")
    _allow("WEB", "ANDROID")
