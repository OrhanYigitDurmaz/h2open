# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""accounts: customer ledger and credit limits.

Revision ID: 9abee0bec75b
Revises: 8073958a00c5
Create Date: 2026-11-26 12:39:56.425467+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "9abee0bec75b"
down_revision: str | Sequence[str] | None = "8073958a00c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA accounts")
    _ = op.create_table(
        "credit_limits",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint(
            "amount >= 0", name=op.f("ck_credit_limits_amount_not_negative")
        ),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_credit_limits")),
        schema="accounts",
    )
    _ = op.create_table(
        "entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "CHARGE",
                "PAYMENT",
                "ADJUSTMENT",
                name="entry_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="accounts",
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column(
            "method",
            sa.Enum(
                "CASH",
                "CARD",
                "BANK_TRANSFER",
                name="account_payment_method",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="accounts",
            ),
            nullable=True,
        ),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("override_reason", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "(kind = 'CHARGE') = (order_id IS NOT NULL)",
            name=op.f("ck_entries_charges_have_order"),
        ),
        sa.CheckConstraint(
            "kind <> 'PAYMENT' OR (amount < 0 AND method IS NOT NULL)",
            name=op.f("ck_entries_payments_lower_the_balance"),
        ),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_entries_amount_not_zero")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entries")),
        schema="accounts",
    )
    op.create_index(
        op.f("ix_accounts_entries_customer_id"),
        "entries",
        ["customer_id"],
        unique=False,
        schema="accounts",
    )
    op.create_index(
        op.f("ix_accounts_entries_recorded_by"),
        "entries",
        ["recorded_by"],
        unique=False,
        schema="accounts",
    )
    op.create_index(
        "ux_entries_order", "entries", ["order_id"], unique=True, schema="accounts"
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index("ux_entries_order", table_name="entries", schema="accounts")
    op.drop_index(
        op.f("ix_accounts_entries_recorded_by"), table_name="entries", schema="accounts"
    )
    op.drop_index(
        op.f("ix_accounts_entries_customer_id"), table_name="entries", schema="accounts"
    )
    op.drop_table("entries", schema="accounts")
    op.drop_table("credit_limits", schema="accounts")
    op.execute("DROP SCHEMA accounts")
