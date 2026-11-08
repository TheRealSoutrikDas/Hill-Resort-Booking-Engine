"""Admin promo codes (A-105 to A-107, D-40)."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, PromoCode
from app.services.admin_promos import create_promo, list_promos, update_promo
from app.services.errors import (
    InvalidAdminChange,
    InvalidPromoCode,
    PromoCapTooLow,
    PromoCodeTaken,
    PromoNotFound,
)
from app.services.holds import create_hold
from tests.factories import NOW, RULES, Catalogue, catalogue, guest, line, promo, request, staff

TODAY = NOW.date()
LOCK_MS = RULES.lock_timeout_ms


@pytest.fixture
def admin_id(db: Session) -> int:
    return staff(db, "desk@example.com", team="reservations").id


def create(db: Session, admin_id: int, **kwargs):
    args = dict(
        code="diwali15",
        percent_off=15,
        valid_from=TODAY,
        valid_to=TODAY + timedelta(days=30),
        max_uses=None,
    )
    args.update(kwargs)
    return create_promo(db, actor_id=admin_id, today=TODAY, now=NOW, **args)


def update(db: Session, admin_id: int, code: str, **changes):
    return update_promo(
        db, actor_id=admin_id, code=code, lock_timeout_ms=LOCK_MS, today=TODAY, now=NOW, **changes
    )


def hold_with(db: Session, c: Catalogue, code: str) -> None:
    create_hold(db, guest(db).id, request(line(c.dlx, c.ro)), now=NOW, rules=RULES, promo_code=code)


# ---------- create ----------


def test_create_normalises_and_audits(db: Session, admin_id: int) -> None:
    view = create(db, admin_id, code=" diwali15 ", max_uses=50)
    assert (
        view.code,
        view.percent_off,
        view.max_uses,
        view.used,
        view.uses_left,
        view.usable_today,
    ) == (
        "DIWALI15",
        15,
        50,
        0,
        50,
        True,
    )
    [entry] = db.scalars(select(AuditLog).where(AuditLog.action == "create_promo")).all()
    assert (entry.actor_user_id, entry.entity_id, entry.new_value["percent_off"]) == (
        admin_id,
        "DIWALI15",
        15,
    )


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"code": "D!"}, "invalid_code"),
        ({"percent_off": 0}, "invalid_percent"),
        ({"percent_off": 91}, "invalid_percent"),
        (
            {"valid_to": TODAY - timedelta(days=1), "valid_from": TODAY - timedelta(days=5)},
            "date_in_past",
        ),
        ({"valid_from": TODAY + timedelta(days=5), "valid_to": TODAY}, "range_reversed"),
        ({"max_uses": 0}, "invalid_cap"),
    ],
)
def test_create_rules(db: Session, admin_id: int, kwargs: dict, code: str) -> None:
    with pytest.raises(InvalidAdminChange) as err:
        create(db, admin_id, **kwargs)
    assert err.value.code == code


def test_duplicate_code_is_refused(db: Session, admin_id: int) -> None:
    create(db, admin_id)
    with pytest.raises(PromoCodeTaken):
        create(db, admin_id, code="DIWALI15", percent_off=20)


def test_code_starting_in_the_future_is_not_usable_yet(db: Session, admin_id: int) -> None:
    view = create(db, admin_id, valid_from=TODAY + timedelta(days=3))
    assert view.usable_today is False


# ---------- update ----------


def test_switch_off_end_date_and_remove_cap(db: Session, admin_id: int) -> None:
    create(db, admin_id, max_uses=10)
    view = update(
        db, admin_id, "diwali15", is_active=False, valid_to=TODAY + timedelta(days=5), max_uses=None
    )
    assert (view.is_active, view.valid_to, view.max_uses, view.usable_today) == (
        False,
        TODAY + timedelta(days=5),
        None,
        False,
    )
    [entry] = db.scalars(select(AuditLog).where(AuditLog.action == "update_promo")).all()
    assert entry.old_value == {
        "is_active": True,
        "valid_to": (TODAY + timedelta(days=30)).isoformat(),
        "max_uses": 10,
    }
    assert entry.new_value["max_uses"] is None


def test_fields_not_sent_are_unchanged(db: Session, admin_id: int) -> None:
    create(db, admin_id, max_uses=10)
    view = update(db, admin_id, "DIWALI15", is_active=False)
    assert (view.max_uses, view.valid_to) == (10, TODAY + timedelta(days=30))


def test_no_change_writes_no_audit(db: Session, admin_id: int) -> None:
    create(db, admin_id)
    update(db, admin_id, "DIWALI15", is_active=True)
    assert db.scalars(select(AuditLog).where(AuditLog.action == "update_promo")).all() == []


def test_cap_cannot_go_below_used_plus_reserved(db: Session, admin_id: int) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=10, used_count=3)
    hold_with(db, c, "COFFEE20")
    hold_with(db, c, "COFFEE20")
    with pytest.raises(PromoCapTooLow) as err:
        update(db, admin_id, "COFFEE20", max_uses=4)
    assert (err.value.used, err.value.reserved) == (3, 2)
    assert db.scalar(select(PromoCode.max_uses).where(PromoCode.code == "COFFEE20")) == 10
    assert update(db, admin_id, "COFFEE20", max_uses=5).uses_left == 0


def test_expired_holds_do_not_count_against_the_cap(db: Session, admin_id: int) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=10, used_count=3)
    hold_with(db, c, "COFFEE20")
    later = NOW + timedelta(minutes=11)
    view = update_promo(
        db,
        actor_id=admin_id,
        code="COFFEE20",
        max_uses=3,
        lock_timeout_ms=LOCK_MS,
        today=TODAY,
        now=later,
    )
    assert view.uses_left == 0


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"valid_to": TODAY - timedelta(days=1)}, "date_in_past"),
        ({"max_uses": 0}, "invalid_cap"),
    ],
)
def test_update_rules(db: Session, admin_id: int, changes: dict, code: str) -> None:
    create(db, admin_id, valid_from=TODAY - timedelta(days=10))
    with pytest.raises(InvalidAdminChange) as err:
        update(db, admin_id, "DIWALI15", **changes)
    assert err.value.code == code


def test_end_date_before_start_is_refused(db: Session, admin_id: int) -> None:
    create(db, admin_id, valid_from=TODAY + timedelta(days=10), valid_to=TODAY + timedelta(days=20))
    with pytest.raises(InvalidAdminChange) as err:
        update(db, admin_id, "DIWALI15", valid_to=TODAY + timedelta(days=5))
    assert err.value.code == "range_reversed"


def test_unknown_code(db: Session, admin_id: int) -> None:
    with pytest.raises(PromoNotFound):
        update(db, admin_id, "NOPE", is_active=False)


def test_switched_off_code_stops_new_holds(db: Session, admin_id: int) -> None:
    c = catalogue(db)
    create(db, admin_id)
    update(db, admin_id, "DIWALI15", is_active=False)
    with pytest.raises(InvalidPromoCode) as err:
        hold_with(db, c, "DIWALI15")
    assert err.value.code == "promo_inactive"


# ---------- list ----------


def test_list_shows_uses_reserved_and_usable_today(db: Session, admin_id: int) -> None:
    c = catalogue(db)
    promo(db, "COFFEE20", 20, max_uses=5, used_count=4)
    promo(
        db,
        "MONSOON15",
        15,
        valid_from=TODAY - timedelta(days=60),
        valid_to=TODAY - timedelta(days=1),
    )
    hold_with(db, c, "COFFEE20")
    views = {v.code: v for v in list_promos(db, today=TODAY, now=NOW)}
    coffee = views["COFFEE20"]
    assert (coffee.used, coffee.reserved, coffee.uses_left, coffee.usable_today) == (4, 1, 0, False)
    assert views["MONSOON15"].usable_today is False
