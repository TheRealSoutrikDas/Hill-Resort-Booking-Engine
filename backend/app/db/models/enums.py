"""Allowed values for status and category columns.

Stored as text with a CHECK constraint rather than as Postgres ENUM types, so adding
a value later is a one-line migration.
"""

from enum import StrEnum

from sqlalchemy import CheckConstraint


class UserRole(StrEnum):
    GUEST = "guest"
    STAFF = "staff"


class StaffTeam(StrEnum):
    RESERVATIONS = "reservations"
    EVENTS = "events"


class RoomKind(StrEnum):
    ROOM = "room"
    VILLA = "villa"


class HoldStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"
    RELEASED = "released"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class EnquiryChannel(StrEnum):
    WEB = "web"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    PHONE = "phone"


class EnquiryStatus(StrEnum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class EnquiryCategory(StrEnum):
    ROOM_BOOKING = "room_booking"
    WEDDING = "wedding"
    CORPORATE_OFFSITE = "corporate_offsite"
    COMPLAINT = "complaint"
    OTHER = "other"


class Lane(StrEnum):
    ROOM_BOOKING = "room_booking"
    WEDDING = "wedding"
    CORPORATE_OFFSITE = "corporate_offsite"
    COMPLAINT = "complaint"
    UNSORTED = "unsorted"


class OwnerTeam(StrEnum):
    RESERVATIONS = "reservations"
    EVENTS = "events"
    GM = "gm"


def values_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """CHECK that a column holds one of the enum's values (NULL passes, as in SQL)."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")
