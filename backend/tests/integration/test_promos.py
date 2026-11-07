"""Promo codes (A-14, A-20, A-31, A-54 to A-58, D-30)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyRate, Hold, Payment, PromoCode
from app.services.bookings import PROMO_USED_UP, cancel_booking, confirm_booking
from app.services.errors import InvalidPromoCode
from app.services.holds import create_hold, release_hold, set_guest_details
from tests.factories import NOW, RULES, Catalogue, catalogue, guest, line, promo, request

TODAY = NOW.date()
LATER = NOW + timedelta(minutes=11)


def hold_with(
    db: Session, c: Catalogue, code: str | None, user_id: int | None = None, now=NOW
) -> Hold:
    result = create_hold(
        db, user_id or c.user.id, request(line(c.dlx, c.ro)), now=now, rules=RULES, promo_code=code
    )
    return db.get(Hold, result.hold_id)


def pay_and_confirm(db: Session, hold: Hold, now=NOW):
    set_guest_details(
        db,
        hold.user_id,
        hold.id,
        name="A",
        email="a@example.com",
        phone="+91 00000 00042",
        now=min(now, hold.expires_at - timedelta(seconds=1)),
    )
    payment = Payment(
        hold_id=hold.id, idempotency_key=uuid.uuid4().hex, amount_paise=hold.total_paise
    )
    db.add(payment)
    db.flush()
    return confirm_booking(db, hold.user_id, hold.id, payment.id, now=now, rules=RULES), payment


def used(db: Session, code: str) -> int:
    return db.scalar(select(PromoCode.used_count).where(PromoCode.code == code))


# ---------- validity ----------


def test_valid_code_discounts_every_night_and_is_recorded(db: Session) -> None:
    c = catalogue(db)
    p = promo(db, "WELCOME10", 10)
    hold = hold_with(db, c, "WELCOME10")
    assert hold.promo_code_id == p.id
    assert hold.discount_paise == 2 * 60_000  # 10% of Rs 6,000, two nights
    assert [n.discount_paise for n in hold.items[0].nights] == [60_000, 60_000]
    assert hold.total_paise == hold.subtotal_paise - hold.discount_paise + hold.tax_paise


def test_discount_can_drop_a_night_into_the_lower_gst_slab(db: Session) -> None:
    c = catalogue(db)
    for rate in db.scalars(select(DailyRate).where(DailyRate.room_type_id == c.dlx.id)):
        rate.price_paise = 800_000  # Rs 8,000: 18% without a promo
    db.flush()
    promo(db, "WELCOME10", 10)
    without = hold_with(db, c, None)
    with_code = hold_with(db, c, "WELCOME10")
    assert {n.tax_rate_bp for n in without.items[0].nights} == {1_800}
    assert {n.tax_rate_bp for n in with_code.items[0].nights} == {500}  # Rs 7,200 after 10% (A-08)


def test_code_is_trimmed_and_case_insensitive(db: Session) -> None:
    c = catalogue(db)
    promo(db, "WELCOME10", 10)
    assert hold_with(db, c, "  welcome10 ").promo_code_id is not None


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        (dict(is_active=False), "promo_inactive"),
        (dict(valid_from=TODAY + timedelta(days=1)), "promo_not_started"),
        (
            dict(valid_from=TODAY - timedelta(days=30), valid_to=TODAY - timedelta(days=1)),
            "promo_expired",
        ),
        (dict(max_uses=5, used_count=5), "promo_used_up"),
    ],
    ids=["inactive", "not_started", "expired", "used_up"],
)
def test_unusable_codes_are_rejected_and_nothing_is_held(db: Session, kwargs, code: str) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, **kwargs)
    with pytest.raises(InvalidPromoCode) as err:
        hold_with(db, c, "COFFEE20")
    assert err.value.code == code
    assert db.scalar(select(Hold.id)) is None


def test_unknown_code_is_rejected(db: Session) -> None:
    c = catalogue(db)
    with pytest.raises(InvalidPromoCode) as err:
        hold_with(db, c, "FREESTAY")
    assert err.value.code == "promo_not_found"


def test_last_valid_day_counts(db: Session) -> None:
    c = catalogue(db)
    promo(db, "LASTDAY", 10, valid_from=TODAY - timedelta(days=5), valid_to=TODAY)
    assert hold_with(db, c, "LASTDAY").promo_code_id is not None  # A-31: inclusive


# ---------- uses reserved by holds (A-54) ----------


def test_holds_reserve_uses_and_expiry_gives_them_back(db: Session) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=2, used_count=1)  # one use left
    hold_with(db, c, "COFFEE20")
    with pytest.raises(InvalidPromoCode) as err:
        hold_with(db, c, "COFFEE20", user_id=guest(db).id)
    assert err.value.code == "promo_used_up"
    assert hold_with(db, c, "COFFEE20", user_id=guest(db).id, now=LATER).promo_code_id is not None


def test_release_gives_the_use_back(db: Session) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=1)
    first = hold_with(db, c, "COFFEE20")
    release_hold(db, c.user.id, first.id)
    assert hold_with(db, c, "COFFEE20", user_id=guest(db).id).promo_code_id is not None


def test_no_promo_hold_is_unaffected_by_a_used_up_code(db: Session) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=1, used_count=1)
    assert hold_with(db, c, None).promo_code_id is None


# ---------- counting the use (A-20) ----------


def test_use_is_counted_on_confirmation_once(db: Session) -> None:
    c = catalogue(db)
    promo(db, "WELCOME10", 10, max_uses=10)
    hold = hold_with(db, c, "WELCOME10")
    assert used(db, "WELCOME10") == 0  # holding does not count it
    outcome, payment = pay_and_confirm(db, hold)
    assert outcome.confirmed and used(db, "WELCOME10") == 1
    confirm_booking(db, hold.user_id, hold.id, payment.id, now=NOW, rules=RULES)  # double submit
    assert used(db, "WELCOME10") == 1


def test_cancelling_does_not_give_the_use_back(db: Session) -> None:
    c = catalogue(db)
    promo(db, "WELCOME10", 10)
    outcome, _ = pay_and_confirm(db, hold_with(db, c, "WELCOME10"))
    cancel_booking(db, c.user.id, outcome.booking.reference, now=NOW, rules=RULES)
    assert used(db, "WELCOME10") == 1


def test_code_switched_off_during_the_hold_still_applies(db: Session) -> None:
    c = catalogue(db)
    p = promo(db, "WELCOME10", 10)
    hold = hold_with(db, c, "WELCOME10")
    p.is_active = False
    p.valid_to = TODAY - timedelta(days=1)
    db.flush()
    outcome, _ = pay_and_confirm(db, hold)
    assert outcome.confirmed and outcome.booking.discount_paise == hold.discount_paise  # A-55


def test_expired_hold_whose_last_use_was_taken_is_refunded(db: Session) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=1)
    slow = hold_with(db, c, "COFFEE20")
    hold_with(db, c, "COFFEE20", user_id=guest(db).id, now=LATER)  # takes the freed use

    outcome, payment = pay_and_confirm(db, slow, now=LATER + timedelta(minutes=1))

    assert (outcome.confirmed, outcome.failure) == (False, PROMO_USED_UP)  # A-56
    assert payment.status == "refund_pending" and used(db, "COFFEE20") == 0


def test_active_hold_holding_the_last_use_is_confirmed(db: Session) -> None:
    # Its own reservation must not count against it.
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=1)
    outcome, _ = pay_and_confirm(db, hold_with(db, c, "COFFEE20"))
    assert outcome.confirmed and used(db, "COFFEE20") == 1


def test_expired_hold_with_its_use_still_free_is_confirmed(db: Session) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=1)
    slow = hold_with(db, c, "COFFEE20")
    outcome, _ = pay_and_confirm(db, slow, now=LATER)
    assert outcome.confirmed and used(db, "COFFEE20") == 1
