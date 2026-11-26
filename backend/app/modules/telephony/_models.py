# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Telephony tables, in the ``telephony`` schema. Private to this module."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    MetaData,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import enum_column, module_metadata
from app.core.ids import new_id
from app.modules.telephony._views import CallStatus, EndReason, RingStrategy

SETTINGS_ROW_ID = 1


class Base(DeclarativeBase):
    """Base for telephony tables."""

    metadata: ClassVar[MetaData] = module_metadata("telephony")


class Settings(Base):
    """The single row of telephony settings. Missing means all defaults."""

    __tablename__: str = "settings"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(f"id = {SETTINGS_ROW_ID}", name="single_row"),
        CheckConstraint(
            "driver_ring_delay_seconds BETWEEN 0 AND 300", name="driver_delay_range"
        ),
        CheckConstraint(
            "ring_timeout_seconds BETWEEN 10 AND 600", name="ring_timeout_range"
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ring_strategy: Mapped[RingStrategy] = mapped_column(
        enum_column(RingStrategy, "ring_strategy")
    )
    driver_ring_delay_seconds: Mapped[int] = mapped_column()
    ring_timeout_seconds: Mapped[int] = mapped_column()
    shop_endpoints: Mapped[list[str]] = mapped_column(ARRAY(String(100)))
    driver_endpoint: Mapped[str] = mapped_column(String(100))
    no_answer_sound: Mapped[str | None] = mapped_column(String(100))


class Call(Base):
    """One landline call. Customers and users belong to other modules."""

    __tablename__: str = "calls"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    line: Mapped[str] = mapped_column(String(50))
    caller_number: Mapped[str | None] = mapped_column(String(50), index=True)
    customer_id: Mapped[UUID | None] = mapped_column(index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[CallStatus] = mapped_column(
        enum_column(CallStatus, "call_status"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[str | None] = mapped_column(String(100))
    answered_by_user: Mapped[UUID | None] = mapped_column()
    end_reason: Mapped[EndReason | None] = mapped_column(
        enum_column(EndReason, "end_reason")
    )
