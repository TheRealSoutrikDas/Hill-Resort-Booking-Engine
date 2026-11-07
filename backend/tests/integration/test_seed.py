"""The seed produces exactly the confirmed demo data (A-09) and keeps every invariant."""

from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Allotment,
    Booking,
    DailyRate,
    Enquiry,
    HoldItemNight,
    Payment,
    PromoCode,
    RatePlan,
    RoomType,
    User,
)
from app.enquiry_samples import load_sample_enquiries
from app.seed import plan
from app.seed.build import (
    SeedContext,
    SeedError,
    SeedSummary,
    database_has_data,
    reset_database,
    seed,
    verify,
)
from app.services.pricing import GstRule
from app.services.references import is_valid_booking_reference

TODAY = date(2026, 11, 7)
IST = ZoneInfo("Asia/Kolkata")
CTX = SeedContext(
    today=TODAY,
    now=datetime.combine(TODAY, time(10, 0), tzinfo=IST).astimezone(UTC),
    tz=IST,
    gst_rule=GstRule(threshold_paise=750_000, low_rate_bp=500, high_rate_bp=1_800),
)


def run_seed(db: Session) -> SeedSummary:
    reset_database(db)
    return seed(db, CTX, load_sample_enquiries())


@pytest.fixture
def seeded(db: Session) -> Session:
    run_seed(db)
    return db


def allotment(db: Session, code: str, night: date) -> Allotment:
    return db.scalar(
        select(Allotment)
        .join(RoomType, RoomType.id == Allotment.room_type_id)
        .where(RoomType.code == code, Allotment.stay_date == night)
    )


def ist_date(moment: datetime) -> date:
    return moment.astimezone(IST).date()


# ---------- catalogue and rates ----------


def test_room_counts_match_the_brief(seeded: Session) -> None:
    units = dict(
        seeded.execute(
            select(RoomType.kind, func.sum(RoomType.total_units)).group_by(RoomType.kind)
        ).all()
    )
    assert units == {"room": 64, "villa": 12}


def test_rates_follow_the_plan(seeded: Session) -> None:
    def rate(code: str, plan_code: str, night: date) -> int:
        return seeded.scalar(
            select(DailyRate.price_paise)
            .join(RoomType, RoomType.id == DailyRate.room_type_id)
            .join(RatePlan, RatePlan.id == DailyRate.rate_plan_id)
            .where(RoomType.code == code, RatePlan.code == plan_code, DailyRate.stay_date == night)
        )

    assert rate("DLX", "RO", date(2026, 11, 10)) == 600_000  # Tuesday
    assert rate("DLX", "RO", date(2026, 11, 13)) == 720_000  # Friday +20%
    assert rate("DLX", "RO", date(2026, 12, 25)) == 840_000  # peak +40%
    assert rate("DLX", "BB", date(2026, 11, 10)) == 720_000  # +Rs 1,200


def test_year_average_rate_is_near_9500() -> None:
    nights = [TODAY + timedelta(days=i) for i in range(365)]
    units = sum(rt.units for rt in plan.ROOM_TYPES)
    total = sum(
        rt.units * plan.room_only_rate_rupees(rt.weekday_rate_rupees, night)
        for rt in plan.ROOM_TYPES
        for night in nights
    )
    assert 9_300 <= total / (units * 365) <= 9_700


def test_rates_and_allotments_cover_the_window(seeded: Session) -> None:
    first = TODAY - timedelta(days=60)
    last = TODAY + timedelta(days=179)
    for model in (DailyRate, Allotment):
        low, high = seeded.execute(
            select(func.min(model.stay_date), func.max(model.stay_date))
        ).one()
        assert (low, high) == (first, last)


# ---------- allotment and deliberate states ----------


def test_web_allotment_is_25_percent(seeded: Session) -> None:
    night = TODAY + timedelta(days=3)
    assert {
        code: allotment(seeded, code, night).total_for_web
        for code in ("DLX", "EVR", "FST", "PLV", "PPV")
    } == {
        "DLX": 8,
        "EVR": 6,
        "FST": 3,
        "PLV": 2,
        "PPV": 1,
    }


def test_sold_matches_confirmed_bookings_on_every_night(seeded: Session) -> None:
    expected: Counter[tuple[int, date]] = Counter()
    for booking in seeded.scalars(select(Booking).where(Booking.status == "confirmed")):
        for item in booking.items:
            for i in range((booking.check_out - booking.check_in).days):
                expected[(item.room_type_id, booking.check_in + timedelta(days=i))] += item.units
    actual = {
        (a.room_type_id, a.stay_date): a.sold for a in seeded.scalars(select(Allotment)) if a.sold
    }
    assert actual == dict(expected)


def test_sold_out_weekend(seeded: Session) -> None:
    friday = plan.sold_out_friday(TODAY)
    for night in (friday, friday + timedelta(days=1)):
        for rt in plan.ROOM_TYPES:
            row = allotment(seeded, rt.code, night)
            assert row.sold == row.total_for_web, (rt.code, night)


def test_family_suite_has_exactly_one_unit_left(seeded: Session) -> None:
    friday = plan.one_left_friday(TODAY)
    for night in (friday, friday + timedelta(days=1)):
        row = allotment(seeded, "FST", night)
        assert row.total_for_web - row.sold == 1


def test_blackout_period(seeded: Session) -> None:
    nights = plan.blackout_nights(TODAY)
    assert len(nights) == 3 and nights[0].weekday() == 0
    flagged = seeded.scalars(
        select(Allotment.stay_date).where(Allotment.is_blackout).distinct()
    ).all()
    assert sorted(flagged) == nights
    sold_on_blackout = seeded.scalar(select(func.sum(Allotment.sold)).where(Allotment.is_blackout))
    assert sold_on_blackout == 0


def test_deliberate_dates_are_relative_to_today(seeded: Session) -> None:
    assert plan.one_left_friday(TODAY) == date(2026, 11, 20)
    assert plan.sold_out_friday(TODAY) == date(2026, 11, 27)
    assert plan.blackout_nights(TODAY)[0] == date(2026, 12, 14)


# ---------- bookings ----------


def test_booking_mix(seeded: Session) -> None:
    bookings = seeded.scalars(select(Booking)).all()
    assert len(bookings) == 40
    cancelled = [b for b in bookings if b.status == "cancelled"]
    past = [b for b in bookings if b.status == "confirmed" and b.check_out <= TODAY]
    upcoming = [b for b in bookings if b.status == "confirmed" and b.check_in > TODAY]
    assert (len(past), len(upcoming), len(cancelled)) == (8, 28, 4)
    assert sum(1 for b in bookings if len(b.items) > 1) >= 4  # mixed room types
    assert all(sum(i.units for i in b.items) <= plan.MAX_UNITS_PER_BOOKING for b in bookings)


def test_every_booking_is_internally_consistent(seeded: Session) -> None:
    for booking in seeded.scalars(select(Booking)):
        assert ist_date(booking.confirmed_at) < booking.check_in or booking.status == "cancelled"
        assert booking.subtotal_paise == sum(i.subtotal_paise for i in booking.items)
        assert booking.discount_paise == sum(i.discount_paise for i in booking.items)
        assert booking.tax_paise == sum(i.tax_paise for i in booking.items)
        assert (booking.promo_code_id is None) == (booking.discount_paise == 0)
        payment = seeded.get(Payment, booking.payment_id)
        assert payment.amount_paise == booking.total_paise
        assert payment.status == ("refunded" if booking.status == "cancelled" else "succeeded")
        assert is_valid_booking_reference(booking.reference)


def test_gst_uses_both_slabs(seeded: Session) -> None:
    rates = set(seeded.scalars(select(HoldItemNight.tax_rate_bp).distinct()))
    assert rates == {500, 1_800}


def test_export_dates_have_rows(seeded: Session) -> None:
    yesterday = TODAY - timedelta(days=1)
    bookings = seeded.scalars(select(Booking)).all()
    assert sum(1 for b in bookings if ist_date(b.confirmed_at) == yesterday) >= 3
    assert sum(1 for b in bookings if b.cancelled_at and ist_date(b.cancelled_at) == yesterday) >= 1


def test_promo_codes_cover_valid_expired_and_capped(seeded: Session) -> None:
    promos = {p.code: p for p in seeded.scalars(select(PromoCode))}
    assert promos["WELCOME10"].valid_from <= TODAY <= promos["WELCOME10"].valid_to
    assert promos["MONSOON15"].valid_to < TODAY
    assert promos["COFFEE20"].used_count == promos["COFFEE20"].max_uses == 5
    for promo in promos.values():
        uses = seeded.scalars(select(Booking).where(Booking.promo_code_id == promo.id)).all()
        assert promo.used_count == len(uses)
        for booking in uses:  # each use happened while the code was valid
            assert promo.valid_from <= ist_date(booking.confirmed_at) <= promo.valid_to


# ---------- users and fake data ----------


def test_demo_accounts(seeded: Session) -> None:
    users = {u.email: u for u in seeded.scalars(select(User))}
    assert set(users) == {u.email for u in plan.USERS}
    assert users["gm@example.com"].is_gm and users["gm@example.com"].team is None
    assert {users[e].team for e in ("reservations@example.com", "events@example.com")} == {
        "reservations",
        "events",
    }
    assert all(u.password_hash == plan.UNUSABLE_PASSWORD_HASH for u in users.values())

    guest_bookings = seeded.scalars(
        select(Booking).where(Booking.user_id == users["guest@example.com"].id)
    ).all()
    kinds = sorted(
        "cancelled" if b.status == "cancelled" else ("past" if b.check_out <= TODAY else "upcoming")
        for b in guest_bookings
    )
    assert kinds == ["cancelled", "past", "upcoming"]


def test_all_personal_data_is_obviously_fake(seeded: Session) -> None:
    for booking in seeded.scalars(select(Booking)):
        assert booking.guest_email.endswith("@example.com")
        assert booking.guest_phone.startswith("+91 00000 ")
    for enquiry in seeded.scalars(select(Enquiry)):
        assert enquiry.contact_email is None or enquiry.contact_email.endswith("@example.com")
        assert enquiry.contact_phone is None or enquiry.contact_phone.startswith("+91 00000 ")


# ---------- enquiries ----------


def test_all_sample_enquiries_are_seeded_unchanged(seeded: Session) -> None:
    samples = {e.id: e.message for e in load_sample_enquiries().enquiries}
    seeded_messages = dict(seeded.execute(select(Enquiry.reference, Enquiry.message)).all())
    assert seeded_messages == samples


def test_seeded_enquiries_are_recent_pending_and_consented_on_web(seeded: Session) -> None:
    for enquiry in seeded.scalars(select(Enquiry)):
        assert enquiry.status == "pending"
        assert CTX.now - timedelta(hours=73) <= enquiry.received_at <= CTX.now
        if enquiry.channel == "web":
            assert enquiry.consent_at is not None and enquiry.consent_version == "v1"
    channels = set(seeded.scalars(select(Enquiry.channel).distinct()))
    assert channels == {"web", "email", "whatsapp", "phone"}


# ---------- determinism and safety ----------


def _fingerprint(db: Session) -> list[tuple]:
    return db.execute(
        select(
            Booking.id, Booking.reference, Booking.check_in, Booking.total_paise, Booking.status
        ).order_by(Booking.id)
    ).all()


def test_seed_is_deterministic_and_reset_is_idempotent(db: Session) -> None:
    run_seed(db)
    first = _fingerprint(db)
    run_seed(db)
    assert _fingerprint(db) == first


def test_detects_existing_data(db: Session) -> None:
    reset_database(db)
    assert not database_has_data(db)
    seed(db, CTX, load_sample_enquiries())
    assert database_has_data(db)


def test_self_check_rejects_inconsistent_stock(seeded: Session) -> None:
    row = allotment(seeded, "DLX", plan.one_left_friday(TODAY))
    row.sold -= 1
    seeded.flush()
    with pytest.raises(SeedError, match="sold mismatch"):
        verify(seeded)
