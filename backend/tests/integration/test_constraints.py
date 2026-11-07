"""The database rejects states the services must never create.

These constraints are a backstop: the services check the same rules first, but a bug
in service code still cannot oversell, double-book or store inconsistent money.
"""

import random
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Allotment,
    Booking,
    BookingItem,
    Enquiry,
    GmAlert,
    Hold,
    HoldItem,
    Payment,
    PromoCode,
    RatePlan,
    RoomType,
    User,
)
from app.services.references import generate_booking_reference

STAY = date(2027, 2, 12)
NOW = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


# ---------- small builders: only the columns each table requires ----------


def room_type(db: Session, code: str = "DLX") -> RoomType:
    rt = RoomType(code=code, name="Deluxe", kind="room", total_units=10, max_guests=3)
    db.add(rt)
    db.flush()
    return rt


def rate_plan(db: Session, code: str = "RO") -> RatePlan:
    rp = RatePlan(code=code, name="Room only")
    db.add(rp)
    db.flush()
    return rp


def hold(db: Session, **overrides) -> Hold:
    values = dict(
        check_in=STAY,
        check_out=STAY + timedelta(days=2),
        subtotal_paise=1_900_000,
        discount_paise=0,
        tax_paise=228_000,
        total_paise=2_128_000,
        expires_at=NOW + timedelta(minutes=10),
    )
    values.update(overrides)
    h = Hold(**values)
    db.add(h)
    db.flush()
    return h


def payment(db: Session, h: Hold, key: str | None = None, status: str = "succeeded") -> Payment:
    p = Payment(
        hold_id=h.id,
        idempotency_key=key or uuid.uuid4().hex,
        amount_paise=h.total_paise,
        status=status,
    )
    db.add(p)
    db.flush()
    return p


def booking(db: Session, h: Hold, p: Payment, **overrides) -> Booking:
    values = dict(
        reference="BK-7F3K9QXM",
        hold_id=h.id,
        payment_id=p.id,
        check_in=h.check_in,
        check_out=h.check_out,
        guest_name="Asha Rao",
        guest_email="asha@example.com",
        guest_phone="+91 90000 00001",
        subtotal_paise=h.subtotal_paise,
        discount_paise=h.discount_paise,
        tax_paise=h.tax_paise,
        total_paise=h.total_paise,
        confirmed_at=NOW,
    )
    values.update(overrides)
    b = Booking(**values)
    db.add(b)
    db.flush()
    return b


def staff(db: Session, email: str, **overrides) -> User:
    values = dict(email=email, password_hash="x", full_name="Staff", role="staff")
    values.update(overrides)
    u = User(**values)
    db.add(u)
    db.flush()
    return u


def rejects(db: Session, obj: object | None = None) -> None:
    """Assert that flushing (optionally after adding obj) violates a constraint."""
    if obj is not None:
        db.add(obj)
    with pytest.raises(IntegrityError):
        db.flush()


# ---------- allotment: the overbooking backstop ----------


def test_allotment_cannot_sell_more_than_web_allotment(db: Session) -> None:
    rt = room_type(db)
    rejects(db, Allotment(room_type_id=rt.id, stay_date=STAY, total_for_web=4, sold=5))


def test_allotment_sold_cannot_go_negative(db: Session) -> None:
    # Guards the cancellation path (sold is decremented on cancel).
    rt = room_type(db)
    rejects(db, Allotment(room_type_id=rt.id, stay_date=STAY, total_for_web=4, sold=-1))


def test_one_allotment_row_per_room_type_per_night(db: Session) -> None:
    rt = room_type(db)
    db.add(Allotment(room_type_id=rt.id, stay_date=STAY, total_for_web=4))
    db.flush()
    rejects(db, Allotment(room_type_id=rt.id, stay_date=STAY, total_for_web=2))


# ---------- holds, payments, bookings: the double-booking backstops ----------


def test_stay_must_end_after_it_starts(db: Session) -> None:
    with pytest.raises(IntegrityError):
        hold(db, check_out=STAY)


def test_money_totals_must_add_up(db: Session) -> None:
    with pytest.raises(IntegrityError):
        hold(db, total_paise=1)


def test_discount_cannot_exceed_subtotal(db: Session) -> None:
    with pytest.raises(IntegrityError):
        hold(db, subtotal_paise=100, discount_paise=200, tax_paise=0, total_paise=-100)


def test_same_room_type_and_plan_appear_once_per_hold(db: Session) -> None:
    rt, rp, h = room_type(db), rate_plan(db), hold(db)
    line = dict(
        hold_id=h.id,
        room_type_id=rt.id,
        rate_plan_id=rp.id,
        units=1,
        guests=2,
        subtotal_paise=1,
        tax_paise=0,
    )
    db.add(HoldItem(line_number=1, **line))
    db.flush()
    rejects(db, HoldItem(line_number=2, **line))


def test_idempotency_key_is_unique(db: Session) -> None:
    h = hold(db)
    payment(db, h, key="checkout-abc", status="failed")
    with pytest.raises(IntegrityError):
        payment(db, h, key="checkout-abc", status="pending")


def test_failed_attempts_allowed_but_only_one_captured_payment_per_hold(db: Session) -> None:
    h = hold(db)
    payment(db, h, status="failed")
    payment(db, h, status="succeeded")
    with pytest.raises(IntegrityError):
        payment(db, h, status="succeeded")


def test_one_booking_per_hold(db: Session) -> None:
    h = hold(db)
    booking(db, h, payment(db, h, status="succeeded"))
    other_payment = payment(db, hold(db))
    with pytest.raises(IntegrityError):
        booking(db, h, other_payment, reference="BK-AAAAAAAA")


def test_booking_reference_is_unique(db: Session) -> None:
    h1, h2 = hold(db), hold(db)
    booking(db, h1, payment(db, h1))
    with pytest.raises(IntegrityError):
        booking(db, h2, payment(db, h2))  # same default reference


@pytest.mark.parametrize("reference", ["BK-7F3K9QX", "BK-7F3K9QX0", "bk-7f3k9qxm", "7F3K9QXM"])
def test_booking_reference_format_is_enforced(db: Session, reference: str) -> None:
    h = hold(db)
    with pytest.raises(IntegrityError):
        booking(db, h, payment(db, h), reference=reference)


def test_generated_references_pass_the_database_format_check(db: Session) -> None:
    rng = random.Random(1)
    for _ in range(20):
        h = hold(db)
        booking(db, h, payment(db, h), reference=generate_booking_reference(rng))


def test_cancelled_booking_needs_cancelled_at(db: Session) -> None:
    h = hold(db)
    with pytest.raises(IntegrityError):
        booking(db, h, payment(db, h), status="cancelled")


def test_booking_line_number_unique_within_booking(db: Session) -> None:
    rt, rp, h = room_type(db), rate_plan(db), hold(db)
    b = booking(db, h, payment(db, h))
    items = []
    for n, plan in enumerate([rp, rate_plan(db, "BB")], start=1):
        hi = HoldItem(
            hold_id=h.id,
            line_number=n,
            room_type_id=rt.id,
            rate_plan_id=plan.id,
            units=1,
            guests=2,
            subtotal_paise=1,
            tax_paise=0,
        )
        db.add(hi)
        db.flush()
        items.append(hi)
    common = dict(booking_id=b.id, line_number=1, room_type_id=rt.id, units=1, guests=2)
    db.add(
        BookingItem(
            hold_item_id=items[0].id, rate_plan_id=rp.id, subtotal_paise=1, tax_paise=0, **common
        )
    )
    db.flush()
    rejects(
        db,
        BookingItem(
            hold_item_id=items[1].id, rate_plan_id=rp.id, subtotal_paise=1, tax_paise=0, **common
        ),
    )


# ---------- promo codes ----------


def test_promo_usage_cannot_exceed_cap(db: Session) -> None:
    rejects(
        db,
        PromoCode(
            code="MONSOON10",
            percent_off=10,
            valid_from=STAY,
            valid_to=STAY,
            max_uses=5,
            used_count=6,
        ),
    )


def test_promo_code_stored_uppercase(db: Session) -> None:
    rejects(db, PromoCode(code="monsoon10", percent_off=10, valid_from=STAY, valid_to=STAY))


# ---------- users and roles ----------


def test_email_stored_lowercase_and_unique(db: Session) -> None:
    staff(db, "desk@example.com", team="reservations")
    with pytest.raises(IntegrityError):
        staff(db, "Desk@Example.com", team="reservations")


def test_guest_cannot_be_gm_or_have_team(db: Session) -> None:
    rejects(
        db,
        User(email="g@example.com", password_hash="x", full_name="G", role="guest", is_gm=True),
    )


def test_staff_needs_team_unless_gm(db: Session) -> None:
    with pytest.raises(IntegrityError):
        staff(db, "noteam@example.com")


def test_only_one_gm_account(db: Session) -> None:
    staff(db, "gm@example.com", is_gm=True)
    with pytest.raises(IntegrityError):
        staff(db, "gm2@example.com", is_gm=True)


# ---------- enquiries ----------


def test_web_enquiry_requires_consent(db: Session) -> None:
    rejects(db, Enquiry(reference="ENQ-9001", channel="web", message="Villa for 2 nights?"))


def test_whatsapp_enquiry_does_not_need_form_consent(db: Session) -> None:
    db.add(Enquiry(reference="ENQ-9002", channel="whatsapp", message="Villa for 2 nights?"))
    db.flush()


def test_blank_enquiry_message_rejected(db: Session) -> None:
    rejects(db, Enquiry(reference="ENQ-9003", channel="whatsapp", message="   \n "))


def test_enquiry_lane_must_be_known(db: Session) -> None:
    rejects(
        db,
        Enquiry(reference="ENQ-9004", channel="phone", message="Hello", lane="spam"),
    )


def test_one_gm_alert_per_enquiry(db: Session) -> None:
    e = Enquiry(reference="ENQ-9005", channel="email", message="Room was dirty")
    db.add(e)
    db.flush()
    db.add(GmAlert(enquiry_id=e.id, reason="complaint"))
    db.flush()
    rejects(db, GmAlert(enquiry_id=e.id, reason="complaint"))
