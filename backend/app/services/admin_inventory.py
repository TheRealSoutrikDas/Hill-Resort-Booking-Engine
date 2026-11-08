"""Admin changes to what the website sells: rates, web allotment and blackouts
(brief screen 6, A-100 to A-106, D-39).

Allotment and blackout changes take the same allotment row locks as bookings, in the
same order (D-21), so a guest's hold cannot slip in between the check and the change.
Every change is all or nothing and is written to the audit log.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Allotment, DailyRate, RatePlan, RoomType
from app.services import audit
from app.services.availability import held_units, lock_allotments
from app.services.errors import AllotmentTooLow, BlackoutBlocked, InvalidAdminChange

MAX_CHANGE_NIGHTS = 366
MAX_VIEW_NIGHTS = 62


def nights_between(
    start: date, end: date, *, today: date, max_nights: int, allow_past: bool = False
) -> list[date]:
    """Inclusive range of nights, `start` to `end` (A-101)."""
    if end < start:
        raise InvalidAdminChange("range_reversed", "The end date is before the start date.")
    count = (end - start).days + 1
    if count > max_nights:
        raise InvalidAdminChange("range_too_long", f"Choose at most {max_nights} nights at a time.")
    if not allow_past and start < today:
        raise InvalidAdminChange("date_in_past", "Past nights cannot be changed.")
    return [start + timedelta(days=i) for i in range(count)]


def _room_type(session: Session, code: str) -> RoomType:
    room_type = session.scalar(select(RoomType).where(RoomType.code == code.strip().upper()))
    if room_type is None:
        raise InvalidAdminChange("unknown_room_type", "That room type does not exist.")
    return room_type


def _rate_plan(session: Session, code: str) -> RatePlan:
    rate_plan = session.scalar(select(RatePlan).where(RatePlan.code == code.strip().upper()))
    if rate_plan is None:
        raise InvalidAdminChange("unknown_rate_plan", "That rate plan does not exist.")
    return rate_plan


def _span(nights: Sequence[date]) -> dict[str, str]:
    return {"from": nights[0].isoformat(), "to": nights[-1].isoformat()}


# ---------- calendar view ----------


@dataclass(frozen=True)
class NightView:
    date: date
    total_for_web: int | None  # None: no allotment row, so not on sale (A-37)
    sold: int
    held: int
    available: int
    is_blackout: bool
    rates: dict[str, int | None]  # rate plan code -> price in paise


@dataclass(frozen=True)
class RoomTypeView:
    code: str
    name: str
    total_units: int
    nights: list[NightView]


def inventory(session: Session, nights: Sequence[date], now: datetime) -> list[RoomTypeView]:
    room_types = list(session.scalars(select(RoomType).order_by(RoomType.sort_order, RoomType.id)))
    plans = list(session.scalars(select(RatePlan).order_by(RatePlan.id)))
    ids = [rt.id for rt in room_types]
    rows = {
        (a.room_type_id, a.stay_date): a
        for a in session.scalars(
            select(Allotment).where(
                Allotment.room_type_id.in_(ids), Allotment.stay_date.in_(nights)
            )
        )
    }
    rates = {
        (r.room_type_id, r.rate_plan_id, r.stay_date): r.price_paise
        for r in session.scalars(select(DailyRate).where(DailyRate.stay_date.in_(nights)))
    }
    held = held_units(session, ids, nights, now)
    views = []
    for rt in room_types:
        night_views = []
        for night in nights:
            row = rows.get((rt.id, night))
            sold = row.sold if row else 0
            on_hold = held[(rt.id, night)]
            if row is None or row.is_blackout:
                available = 0
            else:
                available = max(row.total_for_web - sold - on_hold, 0)
            night_views.append(
                NightView(
                    date=night,
                    total_for_web=row.total_for_web if row else None,
                    sold=sold,
                    held=on_hold,
                    available=available,
                    is_blackout=bool(row and row.is_blackout),
                    rates={p.code: rates.get((rt.id, p.id, night)) for p in plans},
                )
            )
        views.append(
            RoomTypeView(code=rt.code, name=rt.name, total_units=rt.total_units, nights=night_views)
        )
    return views


# ---------- rates ----------


def set_rates(
    session: Session,
    *,
    actor_id: int,
    room_type_code: str,
    rate_plan_code: str,
    nights: Sequence[date],
    weekdays: Iterable[int] | None,
    price_paise: int,
    now: datetime,
) -> int:
    """Set a price on these nights (optionally only on some weekdays, 0 = Monday).
    Existing holds and bookings keep their price (A-45, A-104). Returns nights changed."""
    if price_paise <= 0:
        raise InvalidAdminChange("invalid_price", "The price must be more than zero.")
    room_type, rate_plan = _room_type(session, room_type_code), _rate_plan(session, rate_plan_code)
    chosen = set(weekdays) if weekdays is not None else None
    if chosen is not None and not chosen <= set(range(7)):
        raise InvalidAdminChange("invalid_weekday", "Weekdays are 0 (Monday) to 6 (Sunday).")
    targets = [n for n in nights if chosen is None or n.weekday() in chosen]
    if not targets:
        raise InvalidAdminChange(
            "no_matching_nights", "No nights in this range fall on those weekdays."
        )

    old = {
        r.stay_date.isoformat(): r.price_paise
        for r in session.scalars(
            select(DailyRate).where(
                DailyRate.room_type_id == room_type.id,
                DailyRate.rate_plan_id == rate_plan.id,
                DailyRate.stay_date.in_(targets),
            )
        )
    }
    statement = insert(DailyRate).values(
        [
            {
                "room_type_id": room_type.id,
                "rate_plan_id": rate_plan.id,
                "stay_date": n,
                "price_paise": price_paise,
            }
            for n in targets
        ]
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["room_type_id", "rate_plan_id", "stay_date"],
            set_={"price_paise": statement.excluded.price_paise},
        )
    )
    audit.record(
        session,
        actor_id=actor_id,
        entity_type="daily_rate",
        entity_id=f"{room_type.code}/{rate_plan.code}",
        action="set_rates",
        field="price_paise",
        old=old,
        new={
            **_span(nights),
            "weekdays": sorted(chosen) if chosen is not None else None,
            "price_paise": price_paise,
        },
        now=now,
    )
    return len(targets)


# ---------- allotment ----------


def set_allotment(
    session: Session,
    *,
    actor_id: int,
    room_type_code: str,
    nights: Sequence[date],
    total_for_web: int,
    now: datetime,
    lock_timeout_ms: int,
) -> int:
    """Set the web allotment on these nights. It may not go below sold plus active holds
    on any night, nor above the physical units (brief, A-102). Returns nights changed."""
    room_type = _room_type(session, room_type_code)
    if total_for_web < 0:
        raise InvalidAdminChange("negative_allotment", "The allotment cannot be negative.")
    if total_for_web > room_type.total_units:
        raise InvalidAdminChange(
            "above_physical_units", f"{room_type.name} has {room_type.total_units} units in total."
        )
    # Nights without a row yet are created, so they can be locked like the rest.
    session.execute(
        insert(Allotment)
        .values(
            [
                {"room_type_id": room_type.id, "stay_date": n, "total_for_web": 0, "sold": 0}
                for n in nights
            ]
        )
        .on_conflict_do_nothing(index_elements=["room_type_id", "stay_date"])
    )
    rows = lock_allotments(session, [room_type.id], nights, lock_timeout_ms)
    held = held_units(session, [room_type.id], nights, now)
    too_low = []
    for n in nights:
        sold, on_hold = rows[(room_type.id, n)].sold, held[(room_type.id, n)]
        if sold + on_hold > total_for_web:
            too_low.append(
                {"date": n.isoformat(), "sold": sold, "held": on_hold, "minimum": sold + on_hold}
            )
    if too_low:
        raise AllotmentTooLow(too_low)  # nothing is changed: the request rolls back

    old = {n.isoformat(): rows[(room_type.id, n)].total_for_web for n in nights}
    for n in nights:
        rows[(room_type.id, n)].total_for_web = total_for_web
    audit.record(
        session,
        actor_id=actor_id,
        entity_type="allotment",
        entity_id=room_type.code,
        action="set_allotment",
        field="total_for_web",
        old=old,
        new={**_span(nights), "total_for_web": total_for_web},
        now=now,
    )
    return len(nights)


# ---------- blackouts ----------


@dataclass(frozen=True)
class BlackoutResult:
    nights_changed: int
    nights_with_bookings: int  # confirmed bookings on blacked-out nights are honoured


def set_blackout(
    session: Session,
    *,
    actor_id: int,
    room_type_codes: Sequence[str] | None,
    nights: Sequence[date],
    blackout: bool,
    now: datetime,
    lock_timeout_ms: int,
) -> BlackoutResult:
    """Black out (or reopen) these nights for some or all room types (A-103). Blacking
    out is refused while guests hold rooms on those nights; reopening always works.
    Nights with no allotment row are not on sale anyway and are left alone."""
    if room_type_codes is None:
        room_types = list(session.scalars(select(RoomType)))
    else:
        room_types = [_room_type(session, code) for code in room_type_codes]
    codes = {rt.id: rt.code for rt in room_types}
    rows = lock_allotments(session, codes, nights, lock_timeout_ms)
    if blackout:
        held = held_units(session, codes, nights, now)
        busy = [
            {"room_type": codes[rt_id], "date": night.isoformat(), "held": held[(rt_id, night)]}
            for (rt_id, night) in sorted(rows)
            if held[(rt_id, night)] > 0
        ]
        if busy:
            raise BlackoutBlocked(busy)

    old = {
        f"{codes[rt_id]}/{night.isoformat()}": row.is_blackout
        for (rt_id, night), row in sorted(rows.items())
    }
    for row in rows.values():
        row.is_blackout = blackout
    audit.record(
        session,
        actor_id=actor_id,
        entity_type="allotment",
        entity_id=",".join(sorted(codes.values())),
        action="set_blackout",
        field="is_blackout",
        old=old,
        new={**_span(nights), "is_blackout": blackout},
        now=now,
    )
    return BlackoutResult(
        nights_changed=len(rows),
        nights_with_bookings=sum(1 for row in rows.values() if row.sold > 0),
    )
