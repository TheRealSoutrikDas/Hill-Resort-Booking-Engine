"""Admin: rates, web allotment and blackouts (brief screen 6, A-100 to A-106).

Reservations team and the GM only. Every change is audited.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession, Now, Rules
from app.api.errors import ErrorResponse
from app.api.security import require_user
from app.db.models import User
from app.services import admin_inventory as service
from app.services.dates import business_today

router = APIRouter(prefix="/api/admin", tags=["admin"])

AdminUser = Annotated[User, Depends(require_user(role="staff", team="reservations"))]

ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


class NightOut(BaseModel):
    date: date
    total_for_web: int | None
    sold: int
    held: int
    available: int
    is_blackout: bool
    rates: dict[str, int | None]


class RoomTypeInventory(BaseModel):
    code: str
    name: str
    total_units: int
    nights: list[NightOut]


class Inventory(BaseModel):
    from_date: date
    to_date: date
    room_types: list[RoomTypeInventory]


class RangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date
    to_date: date


class RatesIn(RangeIn):
    room_type: str = Field(max_length=32)
    rate_plan: str = Field(max_length=32)
    price_paise: int
    weekdays: list[int] | None = Field(default=None, description="0 = Monday ... 6 = Sunday")


class AllotmentIn(RangeIn):
    room_type: str = Field(max_length=32)
    total_for_web: int


class BlackoutIn(RangeIn):
    room_types: list[str] | None = Field(default=None, description="Omit for all room types")
    blackout: bool


class ChangeOut(BaseModel):
    nights_changed: int


class BlackoutOut(ChangeOut):
    nights_with_bookings: int  # confirmed bookings on those nights are honoured


def _nights(body: RangeIn, now, rules) -> list[date]:
    return service.nights_between(
        body.from_date,
        body.to_date,
        today=business_today(now, rules.tz),
        max_nights=service.MAX_CHANGE_NIGHTS,
    )


@router.get("/inventory", response_model=Inventory, responses=ERRORS)
def admin_inventory(
    user: AdminUser,
    db: DbSession,
    now: Now,
    rules: Rules,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
) -> Inventory:
    """The admin calendar: stock, holds, blackouts and rates per room type per night."""
    nights = service.nights_between(
        from_date,
        to_date,
        today=business_today(now, rules.tz),
        max_nights=service.MAX_VIEW_NIGHTS,
        allow_past=True,
    )
    views = service.inventory(db, nights, now)
    return Inventory(
        from_date=from_date,
        to_date=to_date,
        room_types=[
            RoomTypeInventory(
                code=v.code,
                name=v.name,
                total_units=v.total_units,
                nights=[NightOut(**n.__dict__) for n in v.nights],
            )
            for v in views
        ],
    )


@router.put("/rates", response_model=ChangeOut, responses=ERRORS)
def set_rates(body: RatesIn, user: AdminUser, db: DbSession, now: Now, rules: Rules) -> ChangeOut:
    """Set a price over a date range; existing holds and bookings keep theirs (A-104)."""
    changed = service.set_rates(
        db,
        actor_id=user.id,
        room_type_code=body.room_type,
        rate_plan_code=body.rate_plan,
        nights=_nights(body, now, rules),
        weekdays=body.weekdays,
        price_paise=body.price_paise,
        now=now,
    )
    return ChangeOut(nights_changed=changed)


@router.put("/allotment", response_model=ChangeOut, responses=ERRORS)
def set_allotment(
    body: AllotmentIn, user: AdminUser, db: DbSession, now: Now, rules: Rules
) -> ChangeOut:
    """Set the web allotment; never below sold plus active holds (brief, A-102)."""
    changed = service.set_allotment(
        db,
        actor_id=user.id,
        room_type_code=body.room_type,
        nights=_nights(body, now, rules),
        total_for_web=body.total_for_web,
        now=now,
        lock_timeout_ms=rules.lock_timeout_ms,
    )
    return ChangeOut(nights_changed=changed)


@router.put("/blackouts", response_model=BlackoutOut, responses=ERRORS)
def set_blackouts(
    body: BlackoutIn, user: AdminUser, db: DbSession, now: Now, rules: Rules
) -> BlackoutOut:
    """Black out or reopen nights; refused while guests hold rooms on them (A-103)."""
    result = service.set_blackout(
        db,
        actor_id=user.id,
        room_type_codes=body.room_types,
        nights=_nights(body, now, rules),
        blackout=body.blackout,
        now=now,
        lock_timeout_ms=rules.lock_timeout_ms,
    )
    return BlackoutOut(
        nights_changed=result.nights_changed, nights_with_bookings=result.nights_with_bookings
    )
