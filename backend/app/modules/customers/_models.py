# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Customer tables, in the ``customers`` schema. Private to this module."""

from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.db import module_metadata
from app.core.ids import new_id


class Base(DeclarativeBase):
    """Base for customer tables."""

    metadata: ClassVar[MetaData] = module_metadata("customers")


class Customer(Base):
    """A person or company we sell to. Deactivated, never deleted."""

    __tablename__: str = "customers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), index=True)
    notes: Mapped[str | None] = mapped_column(String(1000))
    active: Mapped[bool] = mapped_column(default=True)

    phones: Mapped[list[Phone]] = relationship(
        order_by="Phone.id", cascade="all, delete-orphan"
    )
    addresses: Mapped[list[Address]] = relationship(
        order_by="Address.id", cascade="all, delete-orphan"
    )


class Address(Base):
    """A delivery address of a customer."""

    __tablename__: str = "addresses"
    __table_args__: tuple[UniqueConstraint, CheckConstraint] = (
        # Lets phones reference (customer_id, id): a phone's default address
        # must belong to the same customer.
        UniqueConstraint("customer_id", "id"),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)", name="coordinates_complete"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey(Customer.id), index=True)
    label: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str] = mapped_column(String(300))
    directions: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))


class Phone(Base):
    """A phone number. Each number belongs to exactly one customer."""

    __tablename__: str = "phones"
    __table_args__: tuple[ForeignKeyConstraint] = (
        ForeignKeyConstraint(
            ["customer_id", "default_address_id"],
            [Address.customer_id, Address.id],
            # Deleting the address clears only the default, not the customer.
            ondelete="SET NULL (default_address_id)",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey(Customer.id), index=True)
    number: Mapped[str] = mapped_column(String(30))
    match_key: Mapped[str] = mapped_column(String(10), unique=True)
    default_address_id: Mapped[UUID | None] = mapped_column()
