# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Company tables, in the ``company`` schema. Private to this module."""

from typing import ClassVar

from sqlalchemy import CheckConstraint, MetaData, SmallInteger, false, text, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import enum_column, module_metadata
from app.modules.company._views import DepositRefundPolicy

SETTINGS_ROW_ID = 1


class Base(DeclarativeBase):
    """Base for company tables."""

    metadata: ClassVar[MetaData] = module_metadata("company")


class Settings(Base):
    """The single row of company settings. Missing means all defaults."""

    __tablename__: str = "settings"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(f"id = {SETTINGS_ROW_ID}", name="single_row"),
        CheckConstraint(
            "unclaimed_alert_minutes BETWEEN 1 AND 1440",
            name="unclaimed_alert_range",
        ),
        CheckConstraint(
            "uncompleted_alert_minutes BETWEEN 1 AND 1440",
            name="uncompleted_alert_range",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    deposit_refund_policy: Mapped[DepositRefundPolicy] = mapped_column(
        enum_column(DepositRefundPolicy, "deposit_refund_policy")
    )
    walk_in_sales_enabled: Mapped[bool] = mapped_column(server_default=true())
    walk_in_deposits_allowed: Mapped[bool] = mapped_column(server_default=false())
    negative_stock_allowed: Mapped[bool] = mapped_column(server_default=true())
    unclaimed_alert_minutes: Mapped[int] = mapped_column(server_default=text("15"))
    uncompleted_alert_minutes: Mapped[int] = mapped_column(server_default=text("120"))
