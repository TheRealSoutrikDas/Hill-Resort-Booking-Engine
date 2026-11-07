"""Phase 1: creating, completing and releasing holds (A-25, A-42 to A-47)."""

import threading
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Allotment, DailyRate, Hold
from app.services.availability import night_availability
from app.services.errors import (
    HoldNotActive,
    HoldNotFound,
    InvalidBookingRequest,
    InvalidStay,
    NotAvailable,
)
from app.services.holds import (
    HoldLineRequest,
    HoldRequest,
    create_hold,
    release_hold,
    set_guest_details,
)
from app.services.pricing import LineInput, price_stay
from tests.factories import (
    DLX_RO,
    FST_RO,
    N2,
    NIGHTS,
    NOW,
    RULES,
    STAY,
    catalogue,
    guest,
    line,
    request,
)


def hold_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Hold))


# ---------- create ----------


def test_creates_hold_with_lines_nights_and_price_snapshot(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(
        db, c.user.id, request(line(c.dlx, c.ro, 2), line(c.fst, c.ro, 1, 3)), now=NOW, rules=RULES
    )
    hold = db.get(Hold, result.hold_id)

    assert hold.status == "active" and hold.user_id == c.user.id
    assert hold.expires_at == NOW + timedelta(minutes=10)
    assert [(i.line_number, i.room_type_id, i.units, i.guests) for i in hold.items] == [
        (1, c.dlx.id, 2, 4),
        (2, c.fst.id, 1, 3),
    ]
    assert [len(i.nights) for i in hold.items] == [2, 2]
    assert [n.tax_rate_bp for n in hold.items[1].nights] == [1_800, 1_800]

    expected = price_stay(
        [LineInput(dict.fromkeys(NIGHTS, DLX_RO), 2), LineInput(dict.fromkeys(NIGHTS, FST_RO), 1)],
        0,
        RULES.gst_rule,
    )
    assert result.price == expected
    assert (hold.subtotal_paise, hold.tax_paise, hold.total_paise) == (
        expected.subtotal_paise,
        expected.tax_paise,
        expected.total_paise,
    )


def test_hold_reserves_stock_without_changing_sold(db: Session) -> None:
    c = catalogue(db)
    create_hold(db, c.user.id, request(line(c.dlx, c.ro, 3)), now=NOW, rules=RULES)
    assert db.scalars(select(Allotment.sold)).all() == [0, 0, 0, 0]
    assert night_availability(db, [c.dlx.id], NIGHTS, NOW) == {
        (c.dlx.id, STAY): 1,
        (c.dlx.id, N2): 1,
    }


def test_expired_hold_gives_the_stock_back(db: Session) -> None:
    c = catalogue(db)
    create_hold(db, c.user.id, request(line(c.dlx, c.ro, 4)), now=NOW, rules=RULES)
    after_expiry = NOW + timedelta(minutes=10)
    assert night_availability(db, [c.dlx.id], [STAY], after_expiry) == {(c.dlx.id, STAY): 4}
    create_hold(db, c.user.id, request(line(c.dlx, c.ro, 4)), now=after_expiry, rules=RULES)


def test_price_is_fixed_when_the_hold_is_created(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    for rate in db.scalars(select(DailyRate)):
        rate.price_paise *= 2
    db.flush()
    assert db.get(Hold, result.hold_id).total_paise == result.price.total_paise


# ---------- all or nothing ----------


def test_one_short_room_type_creates_nothing(db: Session) -> None:
    c = catalogue(db, fst_web=1)
    with pytest.raises(NotAvailable) as err:
        create_hold(
            db, c.user.id, request(line(c.dlx, c.ro, 1), line(c.fst, c.ro, 2)), now=NOW, rules=RULES
        )
    assert {s.room_type_id for s in err.value.shortfalls} == {c.fst.id}
    assert hold_count(db) == 0


def test_one_full_night_rejects_the_whole_stay(db: Session) -> None:
    c = catalogue(db)
    db.scalar(
        select(Allotment).where(Allotment.room_type_id == c.dlx.id, Allotment.stay_date == N2)
    ).sold = 4
    db.flush()
    with pytest.raises(NotAvailable) as err:
        create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    assert [s.stay_date for s in err.value.shortfalls] == [N2]
    assert hold_count(db) == 0


def test_blackout_night_is_not_available(db: Session) -> None:
    c = catalogue(db)
    db.scalar(
        select(Allotment).where(Allotment.room_type_id == c.dlx.id, Allotment.stay_date == STAY)
    ).is_blackout = True
    db.flush()
    with pytest.raises(NotAvailable):
        create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)


# ---------- request rules ----------


def test_missing_rate_for_a_night_is_rejected(db: Session) -> None:
    c = catalogue(db)
    db.delete(db.get(DailyRate, (c.dlx.id, c.ro.id, N2)))
    db.flush()
    with pytest.raises(InvalidBookingRequest) as err:
        create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    assert err.value.code == "rate_unavailable"


@pytest.mark.parametrize(
    ("make_lines", "code"),
    [
        (lambda c: [], "no_lines"),
        (lambda c: [line(c.dlx, c.ro, 0, 1)], "invalid_units"),
        (lambda c: [line(c.dlx, c.ro, 2, 1)], "too_few_guests"),  # A-42
        (lambda c: [line(c.dlx, c.ro, 1, 4)], "too_many_guests"),  # Deluxe takes 3
        (lambda c: [line(c.dlx, c.ro), line(c.dlx, c.ro)], "duplicate_line"),
        (lambda c: [line(c.dlx, c.ro, 3), line(c.fst, c.ro, 2)], "too_many_units"),  # A-25
        (lambda c: [HoldLineRequest(999_999, c.ro.id, 1, 1)], "unknown_room_type"),
        (lambda c: [HoldLineRequest(c.dlx.id, 999_999, 1, 1)], "unknown_rate_plan"),
        (lambda c: [line(c.dlx, c.off)], "rate_plan_inactive"),  # A-46
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_invalid_requests_are_rejected_with_a_code(db: Session, make_lines, code: str) -> None:
    c = catalogue(db)
    with pytest.raises(InvalidBookingRequest) as err:
        create_hold(db, c.user.id, request(*make_lines(c)), now=NOW, rules=RULES)
    assert err.value.code == code
    assert hold_count(db) == 0


def test_two_rate_plans_of_one_room_type_are_separate_lines(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(
        db, c.user.id, request(line(c.dlx, c.ro), line(c.dlx, c.bb)), now=NOW, rules=RULES
    )
    assert len(db.get(Hold, result.hold_id).items) == 2


def test_invalid_dates_are_rejected_before_any_lookup(db: Session) -> None:
    c = catalogue(db)
    past = HoldRequest(
        NOW.date() - timedelta(days=1), NOW.date() + timedelta(days=1), [line(c.dlx, c.ro)]
    )
    with pytest.raises(InvalidStay):
        create_hold(db, c.user.id, past, now=NOW, rules=RULES)


# ---------- guest details ----------


def test_guest_details_are_cleaned_and_saved(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    hold = set_guest_details(
        db,
        c.user.id,
        result.hold_id,
        name="  Asha Rao ",
        email=" Asha@Example.com",
        phone="+91  00000 00042 ",
        now=NOW,
    )
    assert (hold.guest_name, hold.guest_email, hold.guest_phone) == (
        "Asha Rao",
        "asha@example.com",
        "+91 00000 00042",
    )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("name", "   ", "invalid_guest_name"),
        ("email", "not-an-email", "invalid_guest_email"),
        ("phone", "call me", "invalid_guest_phone"),
    ],
)
def test_invalid_guest_details_are_rejected(db: Session, field: str, value: str, code: str) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    details = {"name": "Asha Rao", "email": "asha@example.com", "phone": "+91 00000 00042"}
    details[field] = value
    with pytest.raises(InvalidBookingRequest) as err:
        set_guest_details(db, c.user.id, result.hold_id, now=NOW, **details)
    assert err.value.code == code


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda h: setattr(h, "status", "converted"), "hold_converted"),
        (lambda h: setattr(h, "status", "released"), "hold_released"),
        (lambda h: setattr(h, "expires_at", NOW), "hold_expired"),
    ],
    ids=["converted", "released", "expired"],
)
def test_guest_details_need_an_active_hold(db: Session, change, code: str) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    change(db.get(Hold, result.hold_id))
    db.flush()
    with pytest.raises(HoldNotActive) as err:
        set_guest_details(
            db,
            c.user.id,
            result.hold_id,
            name="A",
            email="a@example.com",
            phone="+91 00000 00042",
            now=NOW,
        )
    assert err.value.code == code


# ---------- ownership (A-43) ----------


def test_another_accounts_hold_is_not_found(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    stranger = guest(db)
    with pytest.raises(HoldNotFound):
        set_guest_details(
            db,
            stranger.id,
            result.hold_id,
            name="A",
            email="a@example.com",
            phone="+91 00000 00042",
            now=NOW,
        )
    with pytest.raises(HoldNotFound):
        release_hold(db, stranger.id, result.hold_id)
    assert db.get(Hold, result.hold_id).status == "active"


def test_unknown_hold_is_not_found(db: Session) -> None:
    c = catalogue(db)
    with pytest.raises(HoldNotFound):
        release_hold(db, c.user.id, uuid4())


# ---------- release (A-44) ----------


def test_release_frees_stock_immediately_and_twice_is_harmless(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro, 4)), now=NOW, rules=RULES)
    assert night_availability(db, [c.dlx.id], [STAY], NOW)[(c.dlx.id, STAY)] == 0
    release_hold(db, c.user.id, result.hold_id)
    release_hold(db, c.user.id, result.hold_id)
    assert db.get(Hold, result.hold_id).status == "released"
    assert night_availability(db, [c.dlx.id], [STAY], NOW)[(c.dlx.id, STAY)] == 4


def test_paid_hold_cannot_be_released(db: Session) -> None:
    c = catalogue(db)
    result = create_hold(db, c.user.id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    db.get(Hold, result.hold_id).status = "converted"
    db.flush()
    with pytest.raises(HoldNotActive) as err:
        release_hold(db, c.user.id, result.hold_id)
    assert err.value.code == "hold_converted"


# ---------- two guests, one last unit ----------


def test_two_guests_racing_for_the_last_unit(committed: sessionmaker[Session]) -> None:
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=1)
        user_ids = (c.user.id, guest(s).id)
        dlx_id, ro_id = c.dlx.id, c.ro.id

    start = threading.Barrier(2)
    outcomes: list[str] = []

    def book(user_id: int) -> None:
        with committed() as s:
            start.wait()
            try:
                with s.begin():
                    create_hold(
                        s,
                        user_id,
                        HoldRequest(STAY, N2, [HoldLineRequest(dlx_id, ro_id, 1, 2)]),
                        now=NOW,
                        rules=RULES,
                    )
                outcomes.append("held")
            except NotAvailable:
                outcomes.append("sold out")

    threads = [threading.Thread(target=book, args=(uid,)) for uid in user_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sorted(outcomes) == ["held", "sold out"]
    with committed() as s:
        assert s.scalar(select(func.count()).select_from(Hold)) == 1
