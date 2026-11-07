"""Promo codes: validity, and uses reserved by holds like rooms (A-54 to A-58, D-30).

    uses left = max_uses - used_count - active holds using the code

A hold reserves a use when it is created (the promo row is locked and checked, so two
guests cannot both take the last use). The use is counted, `used_count + 1`, when the
booking is confirmed (A-20). An expired or released hold gives its use back, the same
lazy way stock comes back. Cancelling a booking does not (A-20).

Lock order, shared with every writer: allotment rows, then the promo row, then the
hold or booking row (D-21).
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.models import Hold, PromoCode
from app.db.models.enums import HoldStatus
from app.services.availability import is_lock_timeout, set_lock_timeout
from app.services.errors import InvalidPromoCode, StockLocked


def normalize_promo_code(code: str) -> str:
    """' coffee20 ' and 'COFFEE20' are the same code (A-57)."""
    return code.strip().upper()


def held_uses(
    session: Session, promo_id: int, now: datetime, exclude_hold_id: UUID | None = None
) -> int:
    """Uses reserved by active, unexpired holds."""
    stmt = (
        select(func.count())
        .select_from(Hold)
        .where(
            Hold.promo_code_id == promo_id,
            Hold.status == HoldStatus.ACTIVE,
            Hold.expires_at > now,
        )
    )
    if exclude_hold_id is not None:
        stmt = stmt.where(Hold.id != exclude_hold_id)
    return session.scalar(stmt) or 0


def uses_left(
    session: Session, promo: PromoCode, now: datetime, exclude_hold_id: UUID | None = None
) -> int | None:
    """None means the code has no usage cap."""
    if promo.max_uses is None:
        return None
    return promo.max_uses - promo.used_count - held_uses(session, promo.id, now, exclude_hold_id)


def check_dates_and_switch(promo: PromoCode, today: date) -> None:
    if not promo.is_active:
        raise InvalidPromoCode("promo_inactive", f"{promo.code} is not available right now.")
    if today < promo.valid_from:
        raise InvalidPromoCode(
            "promo_not_started", f"{promo.code} can be used from {promo.valid_from.isoformat()}."
        )
    if today > promo.valid_to:
        raise InvalidPromoCode("promo_expired", f"{promo.code} has expired.")


def _used_up(promo: PromoCode) -> InvalidPromoCode:
    return InvalidPromoCode(
        "promo_used_up", f"{promo.code} has been fully used. You can continue without it."
    )


def find_promo(session: Session, code: str, *, today: date, now: datetime) -> PromoCode:
    """Look up and validate a code without locking: for quotes shown on screen.
    The authoritative cap check happens under lock in `lock_promo`."""
    promo = session.scalar(select(PromoCode).where(PromoCode.code == normalize_promo_code(code)))
    if promo is None:
        raise InvalidPromoCode("promo_not_found", "That promo code is not valid.")
    check_dates_and_switch(promo, today)
    left = uses_left(session, promo, now)
    if left is not None and left <= 0:
        raise _used_up(promo)
    return promo


def lock_promo(session: Session, promo_id: int, lock_timeout_ms: int) -> PromoCode:
    """Lock the promo row until the transaction ends; reload its values."""
    set_lock_timeout(session, lock_timeout_ms)
    stmt = (
        select(PromoCode)
        .where(PromoCode.id == promo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    try:
        return session.scalars(stmt).one()
    except OperationalError as exc:
        if is_lock_timeout(exc):
            raise StockLocked("Busy, please try again.") from exc
        raise


def reserve_use(
    session: Session, promo_id: int, *, now: datetime, lock_timeout_ms: int
) -> PromoCode:
    """For a new hold: lock the code and make sure a use is left for it."""
    promo = lock_promo(session, promo_id, lock_timeout_ms)
    left = uses_left(session, promo, now)
    if left is not None and left <= 0:
        raise _used_up(promo)
    return promo
