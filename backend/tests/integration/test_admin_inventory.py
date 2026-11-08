"""Admin changes to rates, allotment and blackouts (A-100 to A-106, D-39)."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Allotment, AuditLog, DailyRate, Hold, Payment
from app.services.admin_inventory import (
    MAX_CHANGE_NIGHTS,
    inventory,
    nights_between,
    set_allotment,
    set_blackout,
    set_rates,
)
from app.services.bookings import confirm_booking
from app.services.errors import AllotmentTooLow, BlackoutBlocked, InvalidAdminChange
from app.services.holds import create_hold, set_guest_details
from app.services.quotes import quote_stay
from tests.factories import N2, NIGHTS, NOW, RULES, STAY, Catalogue, catalogue, line, request, staff

TODAY = NOW.date()
LOCK_MS = RULES.lock_timeout_ms


@pytest.fixture
def c(db: Session) -> Catalogue:
    return catalogue(db, dlx_web=4)  # DLX: 10 physical units, 4 on the web; Rs 6,000 Room Only


@pytest.fixture
def admin_id(db: Session) -> int:
    return staff(db, "desk@example.com", team="reservations").id


def row(db: Session, rt_id: int, night: date) -> Allotment:
    return db.scalar(
        select(Allotment).where(Allotment.room_type_id == rt_id, Allotment.stay_date == night)
    )


def hold_dlx(db: Session, c: Catalogue, units: int = 1) -> Hold:
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro, units)), now=NOW, rules=RULES)
    return db.get(Hold, result.hold_id)


def book_dlx(db: Session, c: Catalogue, units: int = 1) -> None:
    hold = hold_dlx(db, c, units)
    set_guest_details(
        db, c.user.id, hold.id, name="A", email="a@example.com", phone="+91 00000 00042", now=NOW
    )
    payment = Payment(
        hold_id=hold.id, idempotency_key=uuid.uuid4().hex, amount_paise=hold.total_paise
    )
    db.add(payment)
    db.flush()
    assert confirm_booking(db, c.user.id, hold.id, payment.id, now=NOW, rules=RULES).confirmed


def audits(db: Session, action: str) -> list[AuditLog]:
    return db.scalars(select(AuditLog).where(AuditLog.action == action)).all()


# ---------- date ranges (A-101) ----------


def test_ranges_are_inclusive_and_checked() -> None:
    assert nights_between(STAY, N2, today=TODAY, max_nights=10) == [STAY, N2]
    for start, end, code in [
        (N2, STAY, "range_reversed"),
        (TODAY - timedelta(days=1), TODAY, "date_in_past"),
        (STAY, STAY + timedelta(days=MAX_CHANGE_NIGHTS), "range_too_long"),
    ]:
        with pytest.raises(InvalidAdminChange) as err:
            nights_between(start, end, today=TODAY, max_nights=MAX_CHANGE_NIGHTS)
        assert err.value.code == code


# ---------- allotment (brief rule, A-102) ----------


def test_allotment_can_go_down_to_sold_plus_held(db: Session, c: Catalogue, admin_id: int) -> None:
    book_dlx(db, c, 1)
    hold_dlx(db, c, 2)
    assert (
        set_allotment(
            db,
            actor_id=admin_id,
            room_type_code="dlx",
            nights=NIGHTS,
            total_for_web=3,
            now=NOW,
            lock_timeout_ms=LOCK_MS,
        )
        == 2
    )
    assert [row(db, c.dlx.id, n).total_for_web for n in NIGHTS] == [3, 3]


def test_allotment_below_sold_plus_held_is_rejected_entirely(
    db: Session, c: Catalogue, admin_id: int
) -> None:
    book_dlx(db, c, 1)
    hold_dlx(db, c, 2)
    with pytest.raises(AllotmentTooLow) as err:
        set_allotment(
            db,
            actor_id=admin_id,
            room_type_code="DLX",
            nights=NIGHTS,
            total_for_web=2,
            now=NOW,
            lock_timeout_ms=LOCK_MS,
        )
    assert err.value.nights == [
        {"date": n.isoformat(), "sold": 1, "held": 2, "minimum": 3} for n in NIGHTS
    ]


def test_expired_holds_do_not_block_a_reduction(db: Session, c: Catalogue, admin_id: int) -> None:
    hold_dlx(db, c, 4)
    later = NOW + timedelta(minutes=11)
    set_allotment(
        db,
        actor_id=admin_id,
        room_type_code="DLX",
        nights=NIGHTS,
        total_for_web=0,
        now=later,
        lock_timeout_ms=LOCK_MS,
    )


@pytest.mark.parametrize(
    ("total", "code"), [(11, "above_physical_units"), (-1, "negative_allotment")]
)
def test_allotment_bounds(db: Session, c: Catalogue, admin_id: int, total: int, code: str) -> None:
    with pytest.raises(InvalidAdminChange) as err:
        set_allotment(
            db,
            actor_id=admin_id,
            room_type_code="DLX",
            nights=NIGHTS,
            total_for_web=total,
            now=NOW,
            lock_timeout_ms=LOCK_MS,
        )
    assert err.value.code == code


def test_missing_nights_are_created(db: Session, c: Catalogue, admin_id: int) -> None:
    new_nights = [STAY + timedelta(days=i) for i in range(2, 5)]
    set_allotment(
        db,
        actor_id=admin_id,
        room_type_code="DLX",
        nights=new_nights,
        total_for_web=5,
        now=NOW,
        lock_timeout_ms=LOCK_MS,
    )
    assert [
        (row(db, c.dlx.id, n).total_for_web, row(db, c.dlx.id, n).sold) for n in new_nights
    ] == [(5, 0)] * 3


def test_allotment_change_is_audited(db: Session, c: Catalogue, admin_id: int) -> None:
    set_allotment(
        db,
        actor_id=admin_id,
        room_type_code="DLX",
        nights=NIGHTS,
        total_for_web=6,
        now=NOW,
        lock_timeout_ms=LOCK_MS,
    )
    [entry] = audits(db, "set_allotment")
    assert (entry.actor_user_id, entry.entity_id, entry.field) == (admin_id, "DLX", "total_for_web")
    assert entry.old_value == {n.isoformat(): 4 for n in NIGHTS}
    assert entry.new_value == {"from": STAY.isoformat(), "to": N2.isoformat(), "total_for_web": 6}


# ---------- blackouts (A-103) ----------


def test_blackout_refused_while_a_guest_holds_rooms(
    db: Session, c: Catalogue, admin_id: int
) -> None:
    hold_dlx(db, c, 1)
    with pytest.raises(BlackoutBlocked) as err:
        set_blackout(
            db,
            actor_id=admin_id,
            room_type_codes=None,
            nights=NIGHTS,
            blackout=True,
            now=NOW,
            lock_timeout_ms=LOCK_MS,
        )
    assert {(n["room_type"], n["held"]) for n in err.value.nights} == {("DLX", 1)}
    assert not row(db, c.dlx.id, STAY).is_blackout


def test_blackout_honours_confirmed_bookings_and_closes_sales(
    db: Session, c: Catalogue, admin_id: int
) -> None:
    book_dlx(db, c, 1)
    result = set_blackout(
        db,
        actor_id=admin_id,
        room_type_codes=["DLX"],
        nights=NIGHTS,
        blackout=True,
        now=NOW,
        lock_timeout_ms=LOCK_MS,
    )
    assert (result.nights_changed, result.nights_with_bookings) == (2, 2)
    assert [row(db, c.dlx.id, n).sold for n in NIGHTS] == [1, 1]  # booking untouched
    assert not row(db, c.fst.id, STAY).is_blackout  # other room type untouched
    views = {v.code: v for v in inventory(db, NIGHTS, NOW)}
    assert [n.available for n in views["DLX"].nights] == [0, 0]


def test_reopening_is_always_allowed(db: Session, c: Catalogue, admin_id: int) -> None:
    for blackout in (True, False):
        set_blackout(
            db,
            actor_id=admin_id,
            room_type_codes=None,
            nights=NIGHTS,
            blackout=blackout,
            now=NOW,
            lock_timeout_ms=LOCK_MS,
        )
    hold_dlx(db, c, 1)
    set_blackout(
        db,
        actor_id=admin_id,
        room_type_codes=None,
        nights=NIGHTS,
        blackout=False,
        now=NOW,
        lock_timeout_ms=LOCK_MS,
    )
    assert len(audits(db, "set_blackout")) == 3


def test_unknown_room_type_is_rejected(db: Session, c: Catalogue, admin_id: int) -> None:
    with pytest.raises(InvalidAdminChange) as err:
        set_blackout(
            db,
            actor_id=admin_id,
            room_type_codes=["PENTHOUSE"],
            nights=NIGHTS,
            blackout=True,
            now=NOW,
            lock_timeout_ms=LOCK_MS,
        )
    assert err.value.code == "unknown_room_type"


# ---------- rates (A-104) ----------


def test_rate_change_affects_new_quotes_not_existing_holds(
    db: Session, c: Catalogue, admin_id: int
) -> None:
    hold = hold_dlx(db, c)
    before = hold.total_paise
    set_rates(
        db,
        actor_id=admin_id,
        room_type_code="DLX",
        rate_plan_code="RO",
        nights=NIGHTS,
        weekdays=None,
        price_paise=900_000,
        now=NOW,
    )
    db.refresh(hold)
    assert hold.total_paise == before
    quote = quote_stay(db, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    assert [n.rate_paise for n in quote.price.lines[0].nights] == [900_000, 900_000]


def test_weekday_rates_hit_only_those_nights(db: Session, c: Catalogue, admin_id: int) -> None:
    week = [STAY + timedelta(days=i) for i in range(7)]  # 12 Feb 2027 is a Friday
    changed = set_rates(
        db,
        actor_id=admin_id,
        room_type_code="DLX",
        rate_plan_code="BB",
        nights=week,
        weekdays=[4, 5],
        price_paise=999_900,
        now=NOW,
    )
    assert changed == 2
    prices = {
        r.stay_date: r.price_paise
        for r in db.scalars(
            select(DailyRate).where(
                DailyRate.room_type_id == c.dlx.id, DailyRate.rate_plan_id == c.bb.id
            )
        )
    }
    assert {d for d, p in prices.items() if p == 999_900} == {STAY, N2}  # Friday and Saturday
    [entry] = audits(db, "set_rates")
    assert entry.old_value == {STAY.isoformat(): 720_000, N2.isoformat(): 720_000}
    assert entry.new_value["weekdays"] == [4, 5]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"price_paise": 0}, "invalid_price"),
        ({"weekdays": [7]}, "invalid_weekday"),
        ({"weekdays": [0]}, "no_matching_nights"),  # 12 and 13 Feb are Friday and Saturday
        ({"rate_plan_code": "XX"}, "unknown_rate_plan"),
    ],
)
def test_rate_rules(db: Session, c: Catalogue, admin_id: int, kwargs: dict, code: str) -> None:
    args = dict(
        room_type_code="DLX", rate_plan_code="RO", nights=NIGHTS, weekdays=None, price_paise=700_000
    )
    args.update(kwargs)
    with pytest.raises(InvalidAdminChange) as err:
        set_rates(db, actor_id=admin_id, now=NOW, **args)
    assert err.value.code == code


# ---------- calendar view ----------


def test_inventory_view(db: Session, c: Catalogue) -> None:
    book_dlx(db, c, 1)
    hold_dlx(db, c, 2)
    views = {v.code: v for v in inventory(db, [*NIGHTS, N2 + timedelta(days=1)], NOW)}
    first = views["DLX"].nights[0]
    assert (first.total_for_web, first.sold, first.held, first.available) == (4, 1, 2, 1)
    assert first.rates == {"RO": 600_000, "BB": 720_000, "OFF": 600_000}
    no_row = views["DLX"].nights[2]
    assert (no_row.total_for_web, no_row.available, no_row.rates["RO"]) == (None, 0, None)
