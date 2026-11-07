"""A signed-in guest's own booking: the confirmation page and cancellation.

Another guest's booking is "not found" (404). Lookup by reference plus email, for
anyone, is in lookup.py and is view only (A-48).
"""

from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Clock, DbSession, Now, Provider, Rules, SessionFactory
from app.api.errors import ErrorResponse
from app.api.holds import GuestDetails
from app.api.schemas import PriceOut, stored_price_out
from app.api.security import GuestUser
from app.db.models import Booking, Hold, Payment, PromoCode
from app.db.models.enums import BookingStatus
from app.services.bookings import get_owned_booking
from app.services.checkout import cancel_and_refund
from app.services.dates import business_today

router = APIRouter(prefix="/api/bookings", tags=["booking"])

ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


class BookingOut(BaseModel):
    reference: str
    status: str
    check_in: date
    check_out: date
    nights: int
    guest: GuestDetails
    price: PriceOut  # the per-night receipt, as charged
    payment_status: str
    payment_reference: str | None
    confirmed_at: datetime
    cancelled_at: datetime | None
    can_cancel: bool  # online cancellation closes the day before check-in (A-51)


def booking_out(db: Session, booking: Booking, now: datetime, rules) -> BookingOut:
    hold = db.get(Hold, booking.hold_id)
    promo = db.get(PromoCode, booking.promo_code_id) if booking.promo_code_id else None
    payment = db.get(Payment, booking.payment_id)
    return BookingOut(
        reference=booking.reference,
        status=booking.status,
        check_in=booking.check_in,
        check_out=booking.check_out,
        nights=(booking.check_out - booking.check_in).days,
        guest=GuestDetails(
            name=booking.guest_name, email=booking.guest_email, phone=booking.guest_phone
        ),
        price=stored_price_out(db, hold.items, promo),
        payment_status=payment.status,
        payment_reference=payment.provider_reference,
        confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at,
        can_cancel=booking.status == BookingStatus.CONFIRMED
        and booking.check_in > business_today(now, rules.tz),
    )


@router.get("/{reference}", response_model=BookingOut, responses=ERRORS)
def get_booking(
    reference: str, user: GuestUser, db: DbSession, now: Now, rules: Rules
) -> BookingOut:
    """The confirmation page and receipt for the booking's own account."""
    return booking_out(db, get_owned_booking(db, user.id, reference), now, rules)


@router.post("/{reference}/cancel", response_model=BookingOut, responses=ERRORS)
def cancel(
    reference: str,
    user: GuestUser,
    db: DbSession,
    factory: SessionFactory,
    provider: Provider,
    rules: Rules,
    clock: Clock,
) -> BookingOut:
    """Cancel, give the rooms back and refund in full (A-33, A-51 to A-53)."""
    cancel_and_refund(factory, provider, user.id, reference, rules=rules, clock=clock)
    return booking_out(db, get_owned_booking(db, user.id, reference), clock(), rules)
