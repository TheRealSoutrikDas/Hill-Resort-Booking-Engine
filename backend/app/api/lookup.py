"""Booking lookup by reference plus email: view only, rate limited (A-48, A-86).

POST with a JSON body, so the email never appears in a URL. The email may be the
booking's guest email or the booking account's email (someone may book for family).
A wrong reference and a wrong email give the same 404, so the route does not reveal
which part was wrong.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.api.deps import DbSession
from app.api.errors import ErrorResponse
from app.api.ratelimit import limit_per_ip
from app.db.models import Booking, Payment, RatePlan, RoomType, User
from app.services.errors import BookingNotFound
from app.services.references import is_valid_booking_reference, normalize_booking_reference
from app.services.validation import normalize_email

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


class LookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(max_length=32)
    email: str = Field(max_length=320)


class LookupLine(BaseModel):
    room_type: str
    room_type_name: str
    rate_plan_name: str
    units: int
    guests: int


class LookupOut(BaseModel):
    reference: str
    status: str
    check_in: date
    check_out: date
    nights: int
    guest_name: str
    guest_email_masked: str  # the phone is never returned here
    lines: list[LookupLine]
    subtotal_paise: int
    discount_paise: int
    gst_paise: int
    total_paise: int
    payment_status: str
    confirmed_at: datetime
    cancelled_at: datetime | None


def mask_email(email: str) -> str:
    """'asha@example.com' -> 'a***@example.com'."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


@router.post(
    "/lookup",
    response_model=LookupOut,
    responses={404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_ip("lookup"))],
)
def lookup_booking(body: LookupIn, db: DbSession) -> LookupOut:
    """View a booking with its reference and email. Cancelling needs signing in (A-48)."""
    reference = normalize_booking_reference(body.reference)
    email = normalize_email(body.email)
    not_found = BookingNotFound("No booking matches that reference and email.")
    if not is_valid_booking_reference(reference):
        raise not_found
    booking = db.scalar(
        select(Booking)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.reference == reference,
            or_(func.lower(Booking.guest_email) == email, User.email == email),
        )
    )
    if booking is None:
        raise not_found
    room_types = {rt.id: rt for rt in db.scalars(select(RoomType))}
    rate_plans = {rp.id: rp for rp in db.scalars(select(RatePlan))}
    return LookupOut(
        reference=booking.reference,
        status=booking.status,
        check_in=booking.check_in,
        check_out=booking.check_out,
        nights=(booking.check_out - booking.check_in).days,
        guest_name=booking.guest_name,
        guest_email_masked=mask_email(booking.guest_email),
        lines=[
            LookupLine(
                room_type=room_types[item.room_type_id].code,
                room_type_name=room_types[item.room_type_id].name,
                rate_plan_name=rate_plans[item.rate_plan_id].name,
                units=item.units,
                guests=item.guests,
            )
            for item in booking.items
        ],
        subtotal_paise=booking.subtotal_paise,
        discount_paise=booking.discount_paise,
        gst_paise=booking.tax_paise,
        total_paise=booking.total_paise,
        payment_status=db.get(Payment, booking.payment_id).status,
        confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at,
    )
