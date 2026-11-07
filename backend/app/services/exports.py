"""The daily booking export for the reservation system (A-10, A-90 to A-95, D-37).

Each row is what happened that day: a confirmation on its IST date, a cancellation on
its IST date, one row per booking line. A day's file therefore never changes once the
day is over, however often it is downloaded, and a cancelled booking shows up as
cancelled in the export of the day it was cancelled (brief).
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Booking, Payment, PromoCode, RatePlan, RoomType

COLUMNS = (
    "booking_id",
    "line_number",
    "status",
    "guest_name",
    "guest_email",
    "guest_phone",
    "check_in",
    "check_out",
    "room_type",
    "rate_plan",
    "guests",
    "amount_paid_paise",
    "tax_paise",
    "payment_status",
    "payment_reference",
    "promo_code",
    "created_at",
)

# The event a row records, and the payment fact that goes with it (A-93).
_PAYMENT_STATUS = {"confirmed": "paid", "cancelled": "refund"}
_EVENT_ORDER = {"confirmed": 0, "cancelled": 1}

# A spreadsheet treats a cell starting with these as a formula (OWASP: CSV injection).
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def neutralise(value: str) -> str:
    """Make free text safe to open in a spreadsheet: a leading apostrophe stops a cell
    such as '=HYPERLINK(...)' from being run as a formula (A-95)."""
    return "'" + value if value.startswith(_FORMULA_STARTS) else value


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The UTC instants where this business day starts and ends (end exclusive)."""
    start = datetime.combine(day, time(0), tzinfo=tz)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


@dataclass(frozen=True)
class _Event:
    at: datetime
    status: str
    booking: Booking


def export_rows(session: Session, day: date, tz: ZoneInfo) -> list[dict[str, str | int]]:
    start, end = day_bounds(day, tz)
    confirmed = session.scalars(
        select(Booking).where(Booking.confirmed_at >= start, Booking.confirmed_at < end)
    )
    cancelled = session.scalars(
        select(Booking).where(Booking.cancelled_at >= start, Booking.cancelled_at < end)
    )
    events = [_Event(b.confirmed_at, "confirmed", b) for b in confirmed]
    events += [_Event(b.cancelled_at, "cancelled", b) for b in cancelled]
    # Stable order, so the same day always gives the same bytes.
    events.sort(key=lambda e: (e.at, _EVENT_ORDER[e.status], e.booking.id))

    room_types = {rt.id: rt.code for rt in session.scalars(select(RoomType))}
    rate_plans = {rp.id: rp.code for rp in session.scalars(select(RatePlan))}
    promos = {p.id: p.code for p in session.scalars(select(PromoCode))}

    rows: list[dict[str, str | int]] = []
    for event in events:
        booking = event.booking
        payment = session.get(Payment, booking.payment_id)
        for item in booking.items:
            rows.append(
                {
                    "booking_id": booking.reference,
                    "line_number": item.line_number,
                    "status": event.status,
                    "guest_name": neutralise(booking.guest_name),
                    "guest_email": neutralise(booking.guest_email),
                    "guest_phone": booking.guest_phone,  # digits, spaces, leading + only (A-49)
                    "check_in": booking.check_in.isoformat(),
                    "check_out": booking.check_out.isoformat(),
                    "room_type": room_types[item.room_type_id],
                    "rate_plan": rate_plans[item.rate_plan_id],
                    "guests": item.guests,
                    "amount_paid_paise": item.subtotal_paise - item.discount_paise + item.tax_paise,
                    "tax_paise": item.tax_paise,
                    "payment_status": _PAYMENT_STATUS[event.status],
                    "payment_reference": payment.provider_reference or "",
                    "promo_code": promos.get(booking.promo_code_id, ""),
                    "created_at": booking.confirmed_at.astimezone(tz).isoformat(timespec="seconds"),
                }
            )
    return rows


def to_csv(rows: list[dict[str, str | int]]) -> str:
    """UTF-8 CSV with a header row and standard quoting (RFC 4180, CRLF line ends)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
