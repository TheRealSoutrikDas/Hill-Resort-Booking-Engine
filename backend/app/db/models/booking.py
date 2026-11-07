"""Holds, payments and confirmed bookings.

Flow: a hold reserves stock for 10 minutes (phase 1); a successful payment converts it
into a booking (phase 2). A booking has one stay (check-in to check-out) and one or more
lines, each a room type, rate plan, number of units and guests.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models._columns import created_at_column, updated_at_column
from app.db.models.enums import BookingStatus, HoldStatus, PaymentStatus, values_check

# Booking references: "BK-" plus 8 characters from this alphabet (no I, L, O, 0 or 1,
# which are easy to misread). Generated randomly; the UNIQUE constraint guarantees
# uniqueness and the service retries on the rare collision.
BOOKING_REFERENCE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
BOOKING_REFERENCE_LENGTH = 8

# Name and SQL of the money checks shared by holds and bookings.
_MONEY_CHECKS = {
    "subtotal_non_negative": "subtotal_paise >= 0",
    "discount_non_negative": "discount_paise >= 0",
    "discount_within_subtotal": "discount_paise <= subtotal_paise",
    "tax_non_negative": "tax_paise >= 0",
    "total_adds_up": "total_paise = subtotal_paise - discount_paise + tax_paise",
}


def _money_constraints() -> tuple[CheckConstraint, ...]:
    return tuple(CheckConstraint(sql, name=name) for name, sql in _MONEY_CHECKS.items())


class Hold(Base):
    """Temporary reservation of stock. Expired holds are ignored lazily, never deleted.

    A hold does not change allotments.sold; only conversion to a booking does.
    """

    __tablename__ = "holds"
    __table_args__ = (
        values_check("status", HoldStatus),
        CheckConstraint("check_out > check_in", name="stay_dates"),
        *_money_constraints(),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Filled in at the guest details step, before payment.
    guest_name: Mapped[str | None] = mapped_column(String(120))
    guest_email: Mapped[str | None] = mapped_column(String(254))
    guest_phone: Mapped[str | None] = mapped_column(String(20))
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id"))
    # Price snapshot taken when the hold is created; payment charges exactly this.
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default=HoldStatus.ACTIVE.value)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    items: Mapped[list["HoldItem"]] = relationship(
        back_populates="hold", cascade="all, delete-orphan", order_by="HoldItem.line_number"
    )


class HoldItem(Base):
    """One line of a hold: a room type on a rate plan, for some units and guests."""

    __tablename__ = "hold_items"
    __table_args__ = (
        UniqueConstraint("hold_id", "line_number"),
        UniqueConstraint("hold_id", "room_type_id", "rate_plan_id"),
        CheckConstraint("line_number > 0", name="line_number_positive"),
        CheckConstraint("units > 0", name="units_positive"),
        CheckConstraint("guests > 0", name="guests_positive"),
        CheckConstraint("subtotal_paise >= 0", name="subtotal_non_negative"),
        CheckConstraint("discount_paise >= 0", name="discount_non_negative"),
        CheckConstraint("discount_paise <= subtotal_paise", name="discount_within_subtotal"),
        CheckConstraint("tax_paise >= 0", name="tax_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hold_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holds.id", ondelete="CASCADE"))
    line_number: Mapped[int] = mapped_column(SmallInteger)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), index=True)
    rate_plan_id: Mapped[int] = mapped_column(ForeignKey("rate_plans.id"))
    units: Mapped[int] = mapped_column(Integer)
    guests: Mapped[int] = mapped_column(Integer)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax_paise: Mapped[int] = mapped_column(BigInteger)

    hold: Mapped[Hold] = relationship(back_populates="items")
    nights: Mapped[list["HoldItemNight"]] = relationship(
        cascade="all, delete-orphan", order_by="HoldItemNight.stay_date"
    )


class HoldItemNight(Base):
    """Per-unit tariff, discount and GST for one night of one line. Never changed after creation;
    the receipt reads it through booking_items.hold_item_id."""

    __tablename__ = "hold_item_nights"
    __table_args__ = (
        CheckConstraint("rate_paise > 0", name="rate_positive"),
        CheckConstraint("discount_paise >= 0", name="discount_non_negative"),
        CheckConstraint("discount_paise <= rate_paise", name="discount_within_rate"),
        CheckConstraint("tax_paise >= 0", name="tax_non_negative"),
        CheckConstraint("tax_rate_bp >= 0", name="tax_rate_non_negative"),
    )

    hold_item_id: Mapped[int] = mapped_column(
        ForeignKey("hold_items.id", ondelete="CASCADE"), primary_key=True
    )
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    rate_paise: Mapped[int] = mapped_column(BigInteger)
    # Promo discount on this unit-night. GST is charged on rate_paise - discount_paise,
    # and the slab is chosen on that same value (A-08).
    discount_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax_paise: Mapped[int] = mapped_column(BigInteger)
    # GST rate applied, in basis points (1200 = 12%), so the receipt shows the rate used.
    tax_rate_bp: Mapped[int] = mapped_column(Integer)


class Payment(Base):
    """A payment attempt against a hold through the (mock) provider.

    A hold may have several attempts (a failure then a retry) but at most one that
    captured money; the partial unique index enforces that.
    """

    __tablename__ = "payments"
    __table_args__ = (
        values_check("status", PaymentStatus),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        Index(
            "uq_payments_one_captured_per_hold",
            "hold_id",
            unique=True,
            postgresql_where=text("status IN ('succeeded', 'refund_pending', 'refunded')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hold_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holds.id"), index=True)
    # Sent by the client per checkout attempt; a double click reuses the same key.
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[str] = mapped_column(String(32), server_default="mock")
    provider_reference: Mapped[str | None] = mapped_column(String(64), unique=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default=PaymentStatus.PENDING.value)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Booking(Base):
    """A confirmed (or later cancelled) booking. Guest details are stored on the booking
    whether or not the guest has an account."""

    __tablename__ = "bookings"
    __table_args__ = (
        values_check("status", BookingStatus),
        CheckConstraint("check_out > check_in", name="stay_dates"),
        CheckConstraint(
            f"reference ~ '^BK-[{BOOKING_REFERENCE_ALPHABET}]{{{BOOKING_REFERENCE_LENGTH}}}$'",
            name="reference_format",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="cancelled_at_matches"
        ),
        *_money_constraints(),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True)
    # One booking per hold and per payment: a double-submitted payment cannot create two.
    hold_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holds.id"), unique=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    guest_name: Mapped[str] = mapped_column(String(120))
    guest_email: Mapped[str] = mapped_column(String(254))
    guest_phone: Mapped[str] = mapped_column(String(20))
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id"))
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default=BookingStatus.CONFIRMED.value)
    # The daily export selects bookings confirmed or cancelled on a given IST date.
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = created_at_column()

    items: Mapped[list["BookingItem"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan", order_by="BookingItem.line_number"
    )


class BookingItem(Base):
    """One line of a booking, copied from its hold line. Exported as one CSV row."""

    __tablename__ = "booking_items"
    __table_args__ = (
        UniqueConstraint("booking_id", "line_number"),
        CheckConstraint("line_number > 0", name="line_number_positive"),
        CheckConstraint("units > 0", name="units_positive"),
        CheckConstraint("guests > 0", name="guests_positive"),
        CheckConstraint("subtotal_paise >= 0", name="subtotal_non_negative"),
        CheckConstraint("discount_paise >= 0", name="discount_non_negative"),
        CheckConstraint("discount_paise <= subtotal_paise", name="discount_within_subtotal"),
        CheckConstraint("tax_paise >= 0", name="tax_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    line_number: Mapped[int] = mapped_column(SmallInteger)
    hold_item_id: Mapped[int] = mapped_column(ForeignKey("hold_items.id"), unique=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    rate_plan_id: Mapped[int] = mapped_column(ForeignKey("rate_plans.id"))
    units: Mapped[int] = mapped_column(Integer)
    guests: Mapped[int] = mapped_column(Integer)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax_paise: Mapped[int] = mapped_column(BigInteger)

    booking: Mapped[Booking] = relationship(back_populates="items")
