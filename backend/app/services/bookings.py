"""Phase 2 of a booking: turn a paid hold into a confirmed booking, and cancel bookings.

Lock order for every write here: the allotment rows first (via the availability
service, ordered by room type and date), then the hold or booking row. Every writer
uses the same order, so they queue instead of deadlocking (D-21).

`confirm_booking` starts after the payment provider has captured the money (the mock
provider arrives in step 10). When money was taken but no booking can be made, the
payment must stay marked `refund_pending`. Raising an error would roll that mark back,
so those cases return a failed outcome instead, and the caller commits either way
(D-27). Errors are raised only when nothing should be saved.

Functions take a Session and never commit.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingItem, Hold, Payment
from app.db.models.enums import BookingStatus, HoldStatus, PaymentStatus
from app.services.availability import StockRequest, lock_allotments, lock_and_check
from app.services.dates import business_today, stay_nights
from app.services.errors import (
    BookingNotFound,
    CancellationNotAllowed,
    NotAvailable,
    PaymentMismatch,
)
from app.services.holds import HoldRules, get_owned_hold
from app.services.references import (
    MAX_REFERENCE_ATTEMPTS,
    generate_booking_reference,
    normalize_booking_reference,
)

# Failure codes returned (not raised) by confirm_booking. All mean "refund the payment".
HOLD_EXPIRED_SOLD_OUT = "hold_expired_sold_out"
STOCK_UNAVAILABLE = "stock_unavailable"
HOLD_RELEASED = "hold_released"
HOLD_ALREADY_PAID = "hold_already_paid"
GUEST_DETAILS_MISSING = "guest_details_missing"
PAYMENT_ALREADY_REFUNDED = "payment_already_refunded"


@dataclass(frozen=True)
class ConfirmOutcome:
    """Either a confirmed booking, or a failure code with the payment marked for refund."""

    booking: Booking | None
    failure: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.booking is not None


def _fail(
    hold: Hold, payment: Payment, code: str, now: datetime, session: Session
) -> ConfirmOutcome:
    """Money was taken but there is no booking: mark it for refund (A-50). The hold is
    released so it cannot be retried."""
    payment.status = PaymentStatus.REFUND_PENDING
    payment.updated_at = now
    if hold.status == HoldStatus.ACTIVE:
        hold.status = HoldStatus.RELEASED
    session.flush()
    return ConfirmOutcome(booking=None, failure=code)


def _insert_booking(
    session: Session,
    hold: Hold,
    payment: Payment,
    now: datetime,
    new_reference: Callable[[], str],
) -> Booking:
    """Insert the booking with a random reference, retrying on the rare collision.

    Each attempt runs in a savepoint, so a duplicate reference only undoes that attempt,
    not the stock changes already made in this transaction (D-14)."""
    for _ in range(MAX_REFERENCE_ATTEMPTS):
        booking = Booking(
            reference=new_reference(),
            hold_id=hold.id,
            payment_id=payment.id,
            user_id=hold.user_id,
            check_in=hold.check_in,
            check_out=hold.check_out,
            guest_name=hold.guest_name,
            guest_email=hold.guest_email,
            guest_phone=hold.guest_phone,
            promo_code_id=hold.promo_code_id,
            subtotal_paise=hold.subtotal_paise,
            discount_paise=hold.discount_paise,
            tax_paise=hold.tax_paise,
            total_paise=hold.total_paise,
            status=BookingStatus.CONFIRMED,
            confirmed_at=now,
            created_at=now,
            items=[
                BookingItem(
                    line_number=item.line_number,
                    hold_item_id=item.id,
                    room_type_id=item.room_type_id,
                    rate_plan_id=item.rate_plan_id,
                    units=item.units,
                    guests=item.guests,
                    subtotal_paise=item.subtotal_paise,
                    discount_paise=item.discount_paise,
                    tax_paise=item.tax_paise,
                )
                for item in hold.items
            ],
        )
        try:
            with session.begin_nested():
                session.add(booking)
                session.flush()
            return booking
        except IntegrityError as exc:
            if (
                getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                != "uq_bookings_reference"
            ):
                raise
    raise RuntimeError(f"no unique booking reference after {MAX_REFERENCE_ATTEMPTS} attempts")


def confirm_booking(
    session: Session,
    user_id: int,
    hold_id: UUID,
    payment_id: int,
    *,
    now: datetime,
    rules: HoldRules,
    new_reference: Callable[[], str] = generate_booking_reference,
) -> ConfirmOutcome:
    """Payment captured: confirm the hold as a booking, or fail and mark the refund.

    Raises (nothing saved): HoldNotFound for another account's hold, PaymentMismatch for
    a payment of another hold or one that was never captured, StockLocked on lock timeout.
    """
    hold = get_owned_hold(session, user_id, hold_id)
    nights = stay_nights(hold.check_in, hold.check_out)
    requests = [StockRequest(item.room_type_id, item.units) for item in hold.items]

    # 1. Allotment rows first. The check leaves this hold out, so its own units count as
    #    available to it; for an expired hold the check is the brief's "is stock still free".
    shortage: NotAvailable | None = None
    try:
        rows = lock_and_check(
            session, requests, nights, now, rules.lock_timeout_ms, exclude_hold_id=hold.id
        )
    except NotAvailable as exc:  # the rows are still locked; decide below
        shortage, rows = exc, {}

    # 2. Then the hold row. Reload hold and payment: they may have changed while we waited.
    hold = get_owned_hold(session, user_id, hold_id, lock=True)
    payment = session.get(Payment, payment_id, populate_existing=True)
    if payment is None or payment.hold_id != hold.id:
        raise PaymentMismatch("payment_not_for_hold", "This payment is not for this booking.")
    if payment.status in (PaymentStatus.FAILED, PaymentStatus.TIMED_OUT):
        raise PaymentMismatch("payment_not_captured", "This payment did not go through.")
    if payment.status in (PaymentStatus.REFUND_PENDING, PaymentStatus.REFUNDED):
        return ConfirmOutcome(booking=None, failure=PAYMENT_ALREADY_REFUNDED)

    # 3. Already paid? The same payment again is a double submit: return the booking.
    existing = session.scalar(select(Booking).where(Booking.hold_id == hold.id))
    if existing is not None:
        if existing.payment_id == payment.id:
            return ConfirmOutcome(booking=existing)
        return _fail(hold, payment, HOLD_ALREADY_PAID, now, session)  # A-50: second payment

    if hold.status == HoldStatus.RELEASED:
        return _fail(hold, payment, HOLD_RELEASED, now, session)
    if not (hold.guest_name and hold.guest_email and hold.guest_phone):
        return _fail(hold, payment, GUEST_DETAILS_MISSING, now, session)
    if shortage is not None:
        expired = hold.expires_at <= now
        return _fail(
            hold, payment, HOLD_EXPIRED_SOLD_OUT if expired else STOCK_UNAVAILABLE, now, session
        )

    # 4. Confirm: sell the units, close the hold, record the payment, create the booking.
    for item in hold.items:
        for night in nights:
            rows[(item.room_type_id, night)].sold += item.units
    hold.status = HoldStatus.CONVERTED
    payment.status = PaymentStatus.SUCCEEDED
    payment.updated_at = now
    booking = _insert_booking(session, hold, payment, now, new_reference)
    return ConfirmOutcome(booking=booking)


def get_owned_booking(
    session: Session, user_id: int, reference: str, *, lock: bool = False
) -> Booking:
    stmt = select(Booking).where(
        Booking.reference == normalize_booking_reference(reference), Booking.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    booking = session.scalar(stmt)
    if booking is None:
        raise BookingNotFound("Booking not found.")
    return booking


def cancel_booking(
    session: Session,
    user_id: int,
    reference: str,
    *,
    now: datetime,
    rules: HoldRules,
) -> Booking:
    """Cancel a confirmed booking and give its stock back (A-51 to A-53).

    Only the account that booked can cancel, until the day before check-in (IST).
    Cancelling twice is harmless. The payment is marked `refund_pending` for a full
    refund (A-33); the promo use is not given back (A-20)."""
    booking = get_owned_booking(session, user_id, reference)
    if booking.status == BookingStatus.CANCELLED:
        return booking
    if booking.check_in <= business_today(now, rules.tz):
        raise CancellationNotAllowed(
            "too_late_to_cancel",
            "Online cancellation closes the day before check-in. Please call us.",
        )

    nights = stay_nights(booking.check_in, booking.check_out)
    rows = lock_allotments(
        session, (item.room_type_id for item in booking.items), nights, rules.lock_timeout_ms
    )
    booking = get_owned_booking(session, user_id, reference, lock=True)
    if booking.status == BookingStatus.CANCELLED:  # cancelled while we waited
        return booking

    for item in booking.items:
        for night in nights:
            row = rows.get((item.room_type_id, night))
            if row is None or row.sold < item.units:
                raise RuntimeError(
                    f"allotment out of step with booking {booking.reference} on {night}"
                )
            row.sold -= item.units
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    payment = session.get(Payment, booking.payment_id)
    payment.status = PaymentStatus.REFUND_PENDING
    payment.updated_at = now
    session.flush()
    return booking
