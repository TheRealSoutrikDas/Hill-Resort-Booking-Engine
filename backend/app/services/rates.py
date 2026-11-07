"""Catalogue lookups for a stay: room types, rate plans and nightly rates.

Read-only and lock-free: rates are not stock, so they are read before the stock lock
is taken, which keeps the locked part of a booking short (D-26).
"""

from collections.abc import Iterable, Sequence
from datetime import date

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.db.models import DailyRate, RatePlan, RoomType


def load_room_types(session: Session, ids: Iterable[int]) -> dict[int, RoomType]:
    return {rt.id: rt for rt in session.scalars(select(RoomType).where(RoomType.id.in_(set(ids))))}


def load_rate_plans(session: Session, ids: Iterable[int]) -> dict[int, RatePlan]:
    return {rp.id: rp for rp in session.scalars(select(RatePlan).where(RatePlan.id.in_(set(ids))))}


def load_nightly_rates(
    session: Session,
    pairs: Iterable[tuple[int, int]],
    nights: Sequence[date],
) -> dict[tuple[int, int, date], int]:
    """Per-unit price in paise for each (room type, rate plan, night) that has a rate.
    Missing keys mean "no rate", which the caller treats as not sellable."""
    pairs = set(pairs)
    if not pairs:
        return {}
    stmt = select(DailyRate).where(
        tuple_(DailyRate.room_type_id, DailyRate.rate_plan_id).in_(pairs),
        DailyRate.stay_date.in_(nights),
    )
    return {
        (r.room_type_id, r.rate_plan_id, r.stay_date): r.price_paise for r in session.scalars(stmt)
    }
