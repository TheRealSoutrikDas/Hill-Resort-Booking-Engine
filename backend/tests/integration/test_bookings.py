"""Phase 2: confirming paid holds, and cancelling bookings (A-33, A-50 to A-53, D-27)."""

import uuid
from datetime import datetime, time, timedelta
from itertools import chain

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Allotment, Booking, Hold, Payment
from app.services.availability import night_availability
from app.services.bookings import (
    GUEST_DETAILS_MISSING,
    HOLD_ALREADY_PAID,
    HOLD_EXPIRED_SOLD_OUT,
    HOLD_RELEASED,
    PAYMENT_ALREADY_REFUNDED,
    STOCK_UNAVAILABLE,
    cancel_booking,
    confirm_booking,
)
from app.services.errors import (
    BookingNotFound,
    CancellationNotAllowed,
    HoldNotFound,
    PaymentMismatch,
)
from app.services.holds import create_hold, release_hold, set_guest_details
from app.services.references import is_valid_booking_reference
from tests.factories import (
    N2,
    NIGHTS,
    NOW,
    RULES,
    STAY,
    Catalogue,
    catalogue,
    guest,
    line,
    request,
)

IST = RULES.tz
LATER = NOW + timedelta(minutes=11)  # after a hold made at NOW has expired


def ready_hold(db: Session, c: Catalogue, *lines, user_id: int | None = None, now=NOW) -> Hold:
    """A hold with guest details: what the guest has right before paying."""
    owner = user_id or c.user.id
    result = create_hold(db, owner, request(*(lines or [line(c.dlx, c.ro)])), now=now, rules=RULES)
    set_guest_details(
        db,
        owner,
        result.hold_id,
        name="Asha Rao",
        email="asha@example.com",
        phone="+91 00000 00042",
        now=now,
    )
    return db.get(Hold, result.hold_id)


def captured(db: Session, hold: Hold) -> Payment:
    """A payment the provider has just captured for this hold (step 10 creates these)."""
    payment = Payment(
        hold_id=hold.id,
        idempotency_key=uuid.uuid4().hex,
        amount_paise=hold.total_paise,
        status="pending",
    )
    db.add(payment)
    db.flush()
    return payment


def sold(db: Session, room_type_id: int) -> list[int]:
    return db.scalars(
        select(Allotment.sold)
        .where(Allotment.room_type_id == room_type_id)
        .order_by(Allotment.stay_date)
    ).all()


def booking_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Booking))


def confirm(db: Session, c: Catalogue, hold: Hold, payment: Payment, now=NOW, user_id=None):
    return confirm_booking(db, user_id or hold.user_id, hold.id, payment.id, now=now, rules=RULES)


# ---------- confirm ----------


def test_confirm_sells_the_units_and_copies_the_hold(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c, line(c.dlx, c.ro, 2), line(c.fst, c.bb, 1, 3))
    payment = captured(db, hold)

    outcome = confirm(db, c, hold, payment)

    assert outcome.confirmed and outcome.failure is None
    booking = outcome.booking
    assert sold(db, c.dlx.id) == [2, 2] and sold(db, c.fst.id) == [1, 1]
    assert hold.status == "converted" and payment.status == "succeeded"
    assert is_valid_booking_reference(booking.reference)
    assert (booking.user_id, booking.status, booking.confirmed_at) == (c.user.id, "confirmed", NOW)
    assert (booking.check_in, booking.check_out) == (hold.check_in, hold.check_out)
    assert (booking.guest_name, booking.guest_email) == ("Asha Rao", "asha@example.com")
    assert (booking.subtotal_paise, booking.tax_paise, booking.total_paise) == (
        hold.subtotal_paise,
        hold.tax_paise,
        hold.total_paise,
    )
    assert [(i.line_number, i.hold_item_id, i.units, i.guests) for i in booking.items] == [
        (h.line_number, h.id, h.units, h.guests) for h in hold.items
    ]


def test_confirmed_units_stay_unavailable(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c, line(c.dlx, c.ro, 3))
    confirm(db, c, hold, captured(db, hold))
    # The converted hold no longer counts; sold does instead.
    assert night_availability(db, [c.dlx.id], NIGHTS, NOW) == {
        (c.dlx.id, STAY): 1,
        (c.dlx.id, N2): 1,
    }


def test_same_payment_twice_returns_the_same_booking(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    payment = captured(db, hold)
    first = confirm(db, c, hold, payment)
    second = confirm(db, c, hold, payment)
    assert second.booking.id == first.booking.id
    assert booking_count(db) == 1 and sold(db, c.dlx.id) == [1, 1]


def test_second_payment_for_a_paid_hold_is_refunded(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    confirm(db, c, hold, captured(db, hold))
    second_payment = captured(db, hold)  # e.g. paid again in another tab

    outcome = confirm(db, c, hold, second_payment)

    assert (outcome.confirmed, outcome.failure) == (False, HOLD_ALREADY_PAID)
    assert second_payment.status == "refund_pending"
    assert booking_count(db) == 1 and sold(db, c.dlx.id) == [1, 1]


def test_expired_hold_is_confirmed_when_stock_is_still_free(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    outcome = confirm(db, c, hold, captured(db, hold), now=LATER)
    assert outcome.confirmed
    assert sold(db, c.dlx.id) == [1, 1]


def test_expired_hold_fails_and_refunds_when_stock_is_gone(db: Session) -> None:
    c = catalogue(db, dlx_web=1)
    slow = ready_hold(db, c)  # holds the last unit, then lets it expire
    payment = captured(db, slow)
    ready_hold(db, c, user_id=guest(db).id, now=LATER)  # someone else takes it

    outcome = confirm(db, c, slow, payment, now=LATER + timedelta(minutes=1))

    assert (outcome.confirmed, outcome.failure) == (False, HOLD_EXPIRED_SOLD_OUT)
    assert payment.status == "refund_pending"
    assert slow.status == "released"
    assert booking_count(db) == 0 and sold(db, c.dlx.id) == [0, 0]


def test_active_hold_fails_if_stock_was_closed_meanwhile(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    payment = captured(db, hold)
    db.scalar(
        select(Allotment).where(Allotment.room_type_id == c.dlx.id, Allotment.stay_date == N2)
    ).is_blackout = True
    db.flush()
    outcome = confirm(db, c, hold, payment)
    assert (outcome.confirmed, outcome.failure) == (False, STOCK_UNAVAILABLE)
    assert payment.status == "refund_pending"


def test_released_hold_fails_and_refunds(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    payment = captured(db, hold)
    release_hold(db, c.user.id, hold.id)
    outcome = confirm(db, c, hold, payment)
    assert (outcome.confirmed, outcome.failure) == (False, HOLD_RELEASED)
    assert payment.status == "refund_pending" and booking_count(db) == 0


def test_missing_guest_details_fails_and_refunds(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    hold = db.get(Hold, result.hold_id)
    payment = captured(db, hold)
    outcome = confirm(db, c, hold, payment)
    assert (outcome.confirmed, outcome.failure) == (False, GUEST_DETAILS_MISSING)
    assert payment.status == "refund_pending" and hold.status == "released"


def test_retrying_a_failed_confirmation_changes_nothing(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    payment = captured(db, hold)
    release_hold(db, c.user.id, hold.id)
    confirm(db, c, hold, payment)
    again = confirm(db, c, hold, payment)
    assert (again.confirmed, again.failure) == (False, PAYMENT_ALREADY_REFUNDED)
    assert booking_count(db) == 0


def test_payment_of_another_hold_is_rejected_and_nothing_changes(db: Session) -> None:
    c = catalogue(db)
    hold, other = ready_hold(db, c), ready_hold(db, c)
    with pytest.raises(PaymentMismatch) as err:
        confirm(db, c, hold, captured(db, other))
    assert err.value.code == "payment_not_for_hold"
    assert hold.status == "active" and booking_count(db) == 0


@pytest.mark.parametrize("status", ["failed", "timed_out"])
def test_uncaptured_payment_is_rejected(db: Session, status: str) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    payment = captured(db, hold)
    payment.status = status
    db.flush()
    with pytest.raises(PaymentMismatch) as err:
        confirm(db, c, hold, payment)
    assert err.value.code == "payment_not_captured"


def test_another_account_cannot_confirm(db: Session) -> None:
    c = catalogue(db)
    hold = ready_hold(db, c)
    with pytest.raises(HoldNotFound):
        confirm(db, c, hold, captured(db, hold), user_id=guest(db).id)
    assert hold.status == "active" and sold(db, c.dlx.id) == [0, 0]


def test_reference_collision_is_retried(db: Session) -> None:
    c = catalogue(db)
    first = ready_hold(db, c)
    taken = confirm(db, c, first, captured(db, first)).booking.reference
    hold = ready_hold(db, c)
    references = chain([taken], ["BK-ABCDEFGH"])

    outcome = confirm_booking(
        db,
        c.user.id,
        hold.id,
        captured(db, hold).id,
        now=NOW,
        rules=RULES,
        new_reference=lambda: next(references),
    )

    assert outcome.booking.reference == "BK-ABCDEFGH"
    assert sold(db, c.dlx.id) == [2, 2]  # the failed attempt did not undo the stock change


# ---------- cancel ----------


def booked(db: Session, c: Catalogue, *lines) -> Booking:
    hold = ready_hold(db, c, *lines)
    return confirm(db, c, hold, captured(db, hold)).booking


def test_cancel_gives_the_stock_back_and_marks_the_refund(db: Session) -> None:
    c = catalogue(db)
    booking = booked(db, c, line(c.dlx, c.ro, 2), line(c.fst, c.ro, 1))
    later = NOW + timedelta(days=1)

    cancelled = cancel_booking(db, c.user.id, booking.reference, now=later, rules=RULES)

    assert (cancelled.status, cancelled.cancelled_at) == ("cancelled", later)
    assert sold(db, c.dlx.id) == [0, 0] and sold(db, c.fst.id) == [0, 0]
    assert db.get(Payment, booking.payment_id).status == "refund_pending"
    assert night_availability(db, [c.dlx.id], [STAY], later)[(c.dlx.id, STAY)] == 4


def test_cancel_accepts_the_reference_as_typed(db: Session) -> None:
    c = catalogue(db)
    booking = booked(db, c)
    cancel_booking(db, c.user.id, f"  {booking.reference.lower()} ", now=NOW, rules=RULES)
    assert booking.status == "cancelled"


def test_cancelling_twice_is_harmless(db: Session) -> None:
    c = catalogue(db)
    booking = booked(db, c)
    first_time = NOW + timedelta(hours=1)
    cancel_booking(db, c.user.id, booking.reference, now=first_time, rules=RULES)
    cancel_booking(
        db, c.user.id, booking.reference, now=first_time + timedelta(hours=1), rules=RULES
    )
    assert booking.cancelled_at == first_time and sold(db, c.dlx.id) == [0, 0]


def test_another_account_cannot_cancel(db: Session) -> None:
    c = catalogue(db)
    booking = booked(db, c)
    with pytest.raises(BookingNotFound):
        cancel_booking(db, guest(db).id, booking.reference, now=NOW, rules=RULES)
    with pytest.raises(BookingNotFound):
        cancel_booking(db, c.user.id, "BK-ZZZZZZZZ", now=NOW, rules=RULES)
    assert booking.status == "confirmed"


def test_cancel_closes_the_day_before_check_in(db: Session) -> None:
    c = catalogue(db)
    booking = booked(db, c)

    def ist(day, hour: int) -> datetime:
        return datetime.combine(day, time(hour), tzinfo=IST)

    with pytest.raises(CancellationNotAllowed) as err:
        cancel_booking(db, c.user.id, booking.reference, now=ist(STAY, 0), rules=RULES)
    assert err.value.code == "too_late_to_cancel"
    cancel_booking(
        db, c.user.id, booking.reference, now=ist(STAY - timedelta(days=1), 23), rules=RULES
    )
    assert booking.status == "cancelled"
