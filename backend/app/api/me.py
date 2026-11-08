"""The signed-in guest's own account pages: My bookings (brief screen 4, A-96 to A-99).

Only bookings made by this account are listed, never bookings matched by email: an
email is unverified, so it must not attach someone else's booking (brief, A-97).
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, Now, Rules
from app.api.errors import ErrorResponse
from app.api.security import GuestUser
from app.db.models import Booking, RatePlan, RoomType
from app.db.models.enums import BookingStatus
from app.services.dates import business_today

router = APIRouter(prefix="/api/me", tags=["account"])

MAX_BOOKINGS = 100  # most recent first; plenty for one resort's guests (A-99)
_SECTION_ORDER = {"upcoming": 0, "current": 1, "past": 2, "cancelled": 3}


class MyBookingLine(BaseModel):
    room_type: str
    room_type_name: str
    rate_plan_name: str
    units: int
    guests: int


class MyBooking(BaseModel):
    reference: str
    status: str
    section: Literal["upcoming", "current", "past", "cancelled"]
    check_in: date
    check_out: date
    nights: int
    lines: list[MyBookingLine]
    total_paise: int
    can_cancel: bool
    confirmed_at: datetime
    cancelled_at: datetime | None


def _section(booking: Booking, today: date) -> str:
    if booking.status == BookingStatus.CANCELLED:
        return "cancelled"
    if booking.check_in > today:
        return "upcoming"
    if booking.check_out > today:
        return "current"
    return "past"


def _order(item: MyBooking) -> tuple:
    """Upcoming and current soonest first; past most recent first; cancelled most
    recently cancelled first."""
    if item.section in ("upcoming", "current"):
        key: float = item.check_in.toordinal()
    elif item.section == "past":
        key = -item.check_out.toordinal()
    else:
        key = -item.cancelled_at.timestamp()
    return (_SECTION_ORDER[item.section], key, item.reference)


@router.get(
    "/bookings",
    response_model=list[MyBooking],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def my_bookings(user: GuestUser, db: DbSession, now: Now, rules: Rules) -> list[MyBooking]:
    """This account's bookings, grouped by section for the My bookings tabs."""
    today = business_today(now, rules.tz)
    bookings = db.scalars(
        select(Booking)
        .where(Booking.user_id == user.id)
        .order_by(Booking.confirmed_at.desc())
        .limit(MAX_BOOKINGS)
    ).all()
    room_types = {rt.id: rt for rt in db.scalars(select(RoomType))}
    rate_plans = {rp.id: rp for rp in db.scalars(select(RatePlan))}
    items = [
        MyBooking(
            reference=b.reference,
            status=b.status,
            section=_section(b, today),
            check_in=b.check_in,
            check_out=b.check_out,
            nights=(b.check_out - b.check_in).days,
            lines=[
                MyBookingLine(
                    room_type=room_types[i.room_type_id].code,
                    room_type_name=room_types[i.room_type_id].name,
                    rate_plan_name=rate_plans[i.rate_plan_id].name,
                    units=i.units,
                    guests=i.guests,
                )
                for i in b.items
            ],
            total_paise=b.total_paise,
            can_cancel=b.status == BookingStatus.CONFIRMED and b.check_in > today,
            confirmed_at=b.confirmed_at,
            cancelled_at=b.cancelled_at,
        )
        for b in bookings
    ]
    return sorted(items, key=_order)
