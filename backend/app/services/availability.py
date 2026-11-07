"""Web stock: how many units the website can still sell, and the row locks that keep
two bookings from selling the same unit (docs/DECISIONS.md D-21).

    available = total_for_web - sold - active hold units   (0 when blacked out)

A night with no allotment row is not sellable online (A-37). A hold is active while its
status is `active` and `expires_at` is in the future; expired holds are ignored here,
never cleaned up (lazy expiry).

Read-only functions serve search pages. Every write (create a hold, convert it, cancel,
change the allotment) first calls `lock_allotments`, so all writers queue on the same
rows. Functions take a Session and never commit: the caller owns the transaction.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.models import Allotment, Hold, HoldItem, HoldItemNight
from app.db.models.enums import HoldStatus
from app.services.errors import NotAvailable, Shortfall, StockLocked

# Postgres error code for "lock_timeout expired" (lock_not_available).
_LOCK_NOT_AVAILABLE = "55P03"


def set_lock_timeout(session: Session, lock_timeout_ms: int) -> None:
    """Limit how long this transaction waits for a row lock (A-41)."""
    # SET does not accept bind parameters; int() keeps the value safe to interpolate.
    session.execute(text(f"SET LOCAL lock_timeout = {int(lock_timeout_ms)}"))


def is_lock_timeout(exc: OperationalError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == _LOCK_NOT_AVAILABLE


Key = tuple[int, date]  # (room_type_id, stay_date)


@dataclass(frozen=True)
class StockRequest:
    """Units of one room type wanted on every night of the stay."""

    room_type_id: int
    units: int


def held_units(
    session: Session,
    room_type_ids: Iterable[int],
    nights: Sequence[date],
    now: datetime,
    exclude_hold_id: UUID | None = None,
) -> Counter[Key]:
    """Units in active, unexpired holds per room type per night."""
    stmt = (
        select(HoldItem.room_type_id, HoldItemNight.stay_date, func.sum(HoldItem.units))
        .join(HoldItemNight, HoldItemNight.hold_item_id == HoldItem.id)
        .join(Hold, Hold.id == HoldItem.hold_id)
        .where(
            Hold.status == HoldStatus.ACTIVE,
            Hold.expires_at > now,
            HoldItem.room_type_id.in_(list(room_type_ids)),
            HoldItemNight.stay_date.in_(list(nights)),
        )
        .group_by(HoldItem.room_type_id, HoldItemNight.stay_date)
    )
    if exclude_hold_id is not None:
        stmt = stmt.where(Hold.id != exclude_hold_id)
    return Counter({(rt, night): int(units) for rt, night, units in session.execute(stmt)})


def _available(row: Allotment | None, held: int) -> int:
    if row is None or row.is_blackout:
        return 0
    return max(row.total_for_web - row.sold - held, 0)


def night_availability(
    session: Session,
    room_type_ids: Sequence[int],
    nights: Sequence[date],
    now: datetime,
) -> dict[Key, int]:
    """Read-only availability per room type per night. No locks; for display only."""
    rows = {
        (row.room_type_id, row.stay_date): row
        for row in session.scalars(
            select(Allotment).where(
                Allotment.room_type_id.in_(room_type_ids), Allotment.stay_date.in_(nights)
            )
        )
    }
    held = held_units(session, room_type_ids, nights, now)
    return {
        (rt, night): _available(rows.get((rt, night)), held[(rt, night)])
        for rt in room_type_ids
        for night in nights
    }


def stay_availability(
    session: Session,
    room_type_ids: Sequence[int],
    nights: Sequence[date],
    now: datetime,
) -> dict[int, int]:
    """Units of each room type free on every night of the stay (the tightest night)."""
    per_night = night_availability(session, room_type_ids, nights, now)
    return {rt: min(per_night[(rt, night)] for night in nights) for rt in room_type_ids}


def lock_allotments(
    session: Session,
    room_type_ids: Iterable[int],
    nights: Sequence[date],
    lock_timeout_ms: int,
) -> dict[Key, Allotment]:
    """Lock the allotment rows for these room types and nights until the transaction ends.

    Rows are locked in one fixed order (room type, then date). Two bookings that need
    overlapping rows therefore always queue in the same order and cannot deadlock.
    Missing rows are simply absent from the result (they mean "not sellable").

    Raises StockLocked if another transaction holds a lock past the timeout; the caller
    must then roll back.
    """
    set_lock_timeout(session, lock_timeout_ms)
    stmt = (
        select(Allotment)
        .where(
            Allotment.room_type_id.in_(sorted(set(room_type_ids))), Allotment.stay_date.in_(nights)
        )
        .order_by(Allotment.room_type_id, Allotment.stay_date)
        .with_for_update()
        # Reload values from the database even if this session loaded the rows before;
        # without this the ORM could hand back numbers read before the lock was taken.
        .execution_options(populate_existing=True)
    )
    try:
        rows = session.scalars(stmt).all()
    except OperationalError as exc:
        if is_lock_timeout(exc):
            raise StockLocked("Stock is busy, please try again.") from exc
        raise
    return {(row.room_type_id, row.stay_date): row for row in rows}


def lock_and_check(
    session: Session,
    requests: Sequence[StockRequest],
    nights: Sequence[date],
    now: datetime,
    lock_timeout_ms: int,
    exclude_hold_id: UUID | None = None,
) -> dict[Key, Allotment]:
    """Lock every row the request touches, then check there is enough stock.

    Returns the locked rows so the caller can update `sold` in the same transaction.
    Raises NotAvailable listing every short night, or StockLocked.

    The hold count runs as its own statement after the lock. Under READ COMMITTED each
    statement sees all data committed before it started, so it includes holds created
    by any booking that held these locks before us.

    `exclude_hold_id` leaves one hold out of the count, so a hold being converted is
    not counted against itself.
    """
    if not requests or not nights:
        raise ValueError("a stock check needs at least one room type and one night")
    wanted: Counter[int] = Counter()
    for request in requests:
        if request.units <= 0:
            raise ValueError("units must be positive")
        wanted[request.room_type_id] += request.units

    rows = lock_allotments(session, wanted, nights, lock_timeout_ms)
    held = held_units(session, wanted, nights, now, exclude_hold_id)
    shortfalls = [
        Shortfall(rt, night, units, available)
        for rt, units in sorted(wanted.items())
        for night in nights
        if (available := _available(rows.get((rt, night)), held[(rt, night)])) < units
    ]
    if shortfalls:
        raise NotAvailable(shortfalls)
    return rows
