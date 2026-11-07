"""Availability arithmetic and the allotment row locks (A-37, A-41, D-21)."""

import threading
import time
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.seed.build import reset_database
from app.services.availability import (
    StockRequest,
    lock_allotments,
    lock_and_check,
    night_availability,
    stay_availability,
)
from app.services.errors import NotAvailable, StockLocked
from tests.factories import NOW, allotment, hold_for_stock, room_type

N1 = date(2027, 2, 12)
N2 = N1 + timedelta(days=1)
NIGHTS = [N1, N2]
LIVE = NOW + timedelta(minutes=10)
EXPIRED = NOW - timedelta(seconds=1)
TIMEOUT_MS = 5_000


# ---------- arithmetic ----------


def test_available_is_total_minus_sold_minus_active_holds(db: Session) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=8, sold=3)
    hold_for_stock(db, [(rt, 2)], [N1], expires_at=LIVE)
    assert night_availability(db, [rt.id], [N1], NOW) == {(rt.id, N1): 3}


@pytest.mark.parametrize(
    ("expires_at", "status"),
    [(EXPIRED, "active"), (LIVE, "converted"), (LIVE, "released")],
    ids=["expired", "converted", "released"],
)
def test_only_active_unexpired_holds_count(db: Session, expires_at, status: str) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=4)
    hold_for_stock(db, [(rt, 3)], [N1], expires_at=expires_at, status=status)
    assert night_availability(db, [rt.id], [N1], NOW)[(rt.id, N1)] == 4


def test_hold_expiring_exactly_now_no_longer_counts(db: Session) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=4)
    hold_for_stock(db, [(rt, 1)], [N1], expires_at=NOW)
    assert night_availability(db, [rt.id], [N1], NOW)[(rt.id, N1)] == 4


def test_blackout_means_zero(db: Session) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=8, is_blackout=True)
    assert night_availability(db, [rt.id], [N1], NOW)[(rt.id, N1)] == 0


def test_missing_allotment_row_means_not_sellable(db: Session) -> None:
    rt = room_type(db)
    assert night_availability(db, [rt.id], [N1], NOW)[(rt.id, N1)] == 0


def test_stay_availability_is_the_tightest_night(db: Session) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=8, sold=2)
    allotment(db, rt, N2, total_for_web=8, sold=7)
    assert stay_availability(db, [rt.id], NIGHTS, NOW) == {rt.id: 1}


def test_holds_only_count_on_their_own_nights_and_room_type(db: Session) -> None:
    dlx, fst = room_type(db, "DLX"), room_type(db, "FST")
    for rt in (dlx, fst):
        for night in NIGHTS:
            allotment(db, rt, night, total_for_web=3)
    hold_for_stock(db, [(dlx, 2)], [N1], expires_at=LIVE)
    assert night_availability(db, [dlx.id, fst.id], NIGHTS, NOW) == {
        (dlx.id, N1): 1,
        (dlx.id, N2): 3,
        (fst.id, N1): 3,
        (fst.id, N2): 3,
    }


# ---------- locked check ----------


def test_lock_and_check_returns_locked_rows_when_enough_stock(db: Session) -> None:
    rt = room_type(db)
    for night in NIGHTS:
        allotment(db, rt, night, total_for_web=2)
    rows = lock_and_check(db, [StockRequest(rt.id, 2)], NIGHTS, NOW, TIMEOUT_MS)
    assert set(rows) == {(rt.id, N1), (rt.id, N2)}


def test_one_full_night_fails_the_whole_stay(db: Session) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=2)
    allotment(db, rt, N2, total_for_web=2, sold=2)
    with pytest.raises(NotAvailable) as err:
        lock_and_check(db, [StockRequest(rt.id, 1)], NIGHTS, NOW, TIMEOUT_MS)
    [shortfall] = err.value.shortfalls
    assert (shortfall.stay_date, shortfall.requested, shortfall.available) == (N2, 1, 0)


def test_two_room_types_where_only_one_is_short(db: Session) -> None:
    dlx, fst = room_type(db, "DLX"), room_type(db, "FST")
    for night in NIGHTS:
        allotment(db, dlx, night, total_for_web=5)
        allotment(db, fst, night, total_for_web=3, sold=2)
    with pytest.raises(NotAvailable) as err:
        lock_and_check(
            db, [StockRequest(dlx.id, 1), StockRequest(fst.id, 2)], NIGHTS, NOW, TIMEOUT_MS
        )
    assert {s.room_type_id for s in err.value.shortfalls} == {fst.id}
    assert len(err.value.shortfalls) == 2  # both nights reported


def test_two_lines_of_one_room_type_are_added_together(db: Session) -> None:
    # Same room type on two rate plans: 2 + 2 units against 3 available.
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=3)
    with pytest.raises(NotAvailable):
        lock_and_check(db, [StockRequest(rt.id, 2), StockRequest(rt.id, 2)], [N1], NOW, TIMEOUT_MS)


def test_missing_row_is_reported_as_a_shortfall(db: Session) -> None:
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=3)
    with pytest.raises(NotAvailable) as err:
        lock_and_check(db, [StockRequest(rt.id, 1)], NIGHTS, NOW, TIMEOUT_MS)
    assert [s.stay_date for s in err.value.shortfalls] == [N2]


def test_excluded_hold_is_not_counted_against_itself(db: Session) -> None:
    # The last unit is held; converting that same hold must still pass.
    rt = room_type(db)
    allotment(db, rt, N1, total_for_web=1)
    h = hold_for_stock(db, [(rt, 1)], [N1], expires_at=LIVE)
    with pytest.raises(NotAvailable):
        lock_and_check(db, [StockRequest(rt.id, 1)], [N1], NOW, TIMEOUT_MS)
    rows = lock_and_check(db, [StockRequest(rt.id, 1)], [N1], NOW, TIMEOUT_MS, exclude_hold_id=h.id)
    assert rows[(rt.id, N1)].total_for_web == 1


def test_lock_reloads_values_changed_since_the_session_read_them(db: Session) -> None:
    rt = room_type(db)
    row = allotment(db, rt, N1, total_for_web=5, sold=1)
    db.execute(
        row.__table__.update().where(row.__table__.c.room_type_id == rt.id).values(sold=4)
    )  # changed behind the ORM's back
    rows = lock_allotments(db, [rt.id], [N1], TIMEOUT_MS)
    assert rows[(rt.id, N1)].sold == 4


@pytest.mark.parametrize("units", [0, -1])
def test_rejects_non_positive_units(db: Session, units: int) -> None:
    with pytest.raises(ValueError):
        lock_and_check(db, [StockRequest(1, units)], [N1], NOW, TIMEOUT_MS)


# ---------- real row locks across two connections ----------


@pytest.fixture
def committed(schema: Engine) -> Iterator[sessionmaker[Session]]:
    """Sessions that really commit, so a second connection can see the rows.
    Every table is emptied afterwards."""
    factory = sessionmaker(bind=schema, expire_on_commit=False)
    try:
        yield factory
    finally:
        with factory() as s, s.begin():
            reset_database(s)


def _stock(factory: sessionmaker[Session]) -> int:
    with factory() as s, s.begin():
        rt = room_type(s)
        allotment(s, rt, N1, total_for_web=1)
        return rt.id


def test_second_writer_waits_for_the_first_to_commit(committed: sessionmaker[Session]) -> None:
    rt_id = _stock(committed)
    waited: list[float] = []

    def second_writer() -> None:
        with committed() as s, s.begin():
            started = time.monotonic()
            lock_allotments(s, [rt_id], [N1], TIMEOUT_MS)
            waited.append(time.monotonic() - started)

    with committed() as first, first.begin():
        lock_allotments(first, [rt_id], [N1], TIMEOUT_MS)
        thread = threading.Thread(target=second_writer)
        thread.start()
        time.sleep(0.5)  # hold the lock while the second writer tries
        assert thread.is_alive(), "second writer should be blocked"
    thread.join(timeout=5)
    assert waited and waited[0] >= 0.4


def test_lock_timeout_fails_fast_with_stock_locked(committed: sessionmaker[Session]) -> None:
    rt_id = _stock(committed)
    with committed() as first, first.begin():
        lock_allotments(first, [rt_id], [N1], TIMEOUT_MS)
        with committed() as second:
            started = time.monotonic()
            with pytest.raises(StockLocked):
                with second.begin():
                    lock_allotments(second, [rt_id], [N1], lock_timeout_ms=200)
            assert time.monotonic() - started < 2
