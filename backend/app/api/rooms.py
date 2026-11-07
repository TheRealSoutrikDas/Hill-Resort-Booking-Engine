"""Public catalogue routes: room search, room detail and quotes (brief screens 1 to 3).

No login and no reservation: every price comes from `quote_stay`, the same code path
that holds use, so the room page, the summary and the hold cannot disagree (D-30).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, Now, Rules
from app.api.errors import ErrorResponse
from app.api.schemas import PriceOut, StayIn, price_out, to_request
from app.db.models import RatePlan, RoomType
from app.services.availability import stay_availability
from app.services.dates import business_today, validate_stay
from app.services.errors import DomainError, InvalidStay, RoomTypeNotFound
from app.services.quotes import HoldLineRequest, HoldRequest, HoldRules, quote_stay

router = APIRouter(prefix="/api", tags=["rooms"])

ERRORS = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class RatePlanOut(BaseModel):
    code: str
    name: str
    description: str


class RoomSummary(BaseModel):
    code: str
    name: str
    kind: str
    description: str
    max_guests: int
    # Only when dates are given (A-85):
    available_units: int | None = None
    fits_guests: bool | None = None
    lowest_total_paise: int | None = None  # one room, cheapest active plan, with GST


class RoomSearch(BaseModel):
    check_in: date | None
    check_out: date | None
    guests: int | None
    rooms: list[RoomSummary]


class PlanQuote(BaseModel):
    rate_plan: RatePlanOut
    price: PriceOut | None  # None when this plan is not on sale for these dates
    unavailable_reason: str | None = None


class RoomDetail(BaseModel):
    room: RoomSummary
    rate_plans: list[RatePlanOut]
    quotes: list[PlanQuote] | None = None  # only when dates are given


def _stay(
    check_in: date | None, check_out: date | None, rules: HoldRules, now
) -> list[date] | None:
    if check_in is None and check_out is None:
        return None
    if check_in is None or check_out is None:
        raise InvalidStay("dates_incomplete", "Choose both check-in and check-out dates.")
    return validate_stay(
        check_in,
        check_out,
        today=business_today(now, rules.tz),
        horizon_days=rules.horizon_days,
        max_nights=rules.max_nights,
    )


def _active_plans(db: Session) -> list[RatePlan]:
    return list(db.scalars(select(RatePlan).where(RatePlan.is_active).order_by(RatePlan.id)))


def _one_room_quote(
    db: Session, rt: RoomType, rp: RatePlan, check_in, check_out, guests, now, rules
):
    request = HoldRequest(
        check_in, check_out, [HoldLineRequest(rt.id, rp.id, 1, min(guests, rt.max_guests))]
    )
    quote = quote_stay(db, request, now=now, rules=rules)
    return request, quote


def _summary(rt: RoomType) -> RoomSummary:
    return RoomSummary(
        code=rt.code,
        name=rt.name,
        kind=rt.kind,
        description=rt.description,
        max_guests=rt.max_guests,
    )


@router.get("/rooms", response_model=RoomSearch, responses=ERRORS)
def search_rooms(
    db: DbSession,
    now: Now,
    rules: Rules,
    check_in: date | None = None,
    check_out: date | None = None,
    guests: Annotated[int, Query(ge=1, le=100)] = 2,
) -> RoomSearch:
    """All room types; with dates, also availability and the lowest price for one room."""
    nights = _stay(check_in, check_out, rules, now)
    room_types = list(db.scalars(select(RoomType).order_by(RoomType.sort_order, RoomType.id)))
    rooms = [_summary(rt) for rt in room_types]
    if nights is not None:
        available = stay_availability(db, [rt.id for rt in room_types], nights, now)
        plans = _active_plans(db)
        for summary, rt in zip(rooms, room_types, strict=True):
            summary.available_units = available[rt.id]
            summary.fits_guests = guests <= rt.max_guests
            totals = []
            for rp in plans:
                try:
                    totals.append(
                        _one_room_quote(db, rt, rp, check_in, check_out, guests, now, rules)[
                            1
                        ].price.total_paise
                    )
                except DomainError:
                    continue  # this plan is not on sale for these dates
            summary.lowest_total_paise = min(totals) if totals else None
    return RoomSearch(
        check_in=check_in, check_out=check_out, guests=guests if nights else None, rooms=rooms
    )


@router.get("/rooms/{code}", response_model=RoomDetail, responses=ERRORS)
def get_room(
    code: str,
    db: DbSession,
    now: Now,
    rules: Rules,
    check_in: date | None = None,
    check_out: date | None = None,
    guests: Annotated[int, Query(ge=1, le=100)] = 2,
) -> RoomDetail:
    """One room type with its rate plans; with dates, a full quote per plan (A-85)."""
    rt = db.scalar(select(RoomType).where(RoomType.code == code.strip().upper()))
    if rt is None:
        raise RoomTypeNotFound("That room type does not exist.")
    nights = _stay(check_in, check_out, rules, now)
    plans = _active_plans(db)
    detail = RoomDetail(
        room=_summary(rt),
        rate_plans=[
            RatePlanOut(code=p.code, name=p.name, description=p.description) for p in plans
        ],
    )
    if nights is None:
        return detail
    detail.room.available_units = stay_availability(db, [rt.id], nights, now)[rt.id]
    detail.room.fits_guests = guests <= rt.max_guests
    detail.quotes = []
    for rp in plans:
        plan_out = RatePlanOut(code=rp.code, name=rp.name, description=rp.description)
        try:
            request, quote = _one_room_quote(db, rt, rp, check_in, check_out, guests, now, rules)
        except DomainError as exc:
            detail.quotes.append(
                PlanQuote(
                    rate_plan=plan_out, price=None, unavailable_reason=getattr(exc, "code", None)
                )
            )
            continue
        detail.quotes.append(
            PlanQuote(
                rate_plan=plan_out,
                price=price_out(quote.price, request, {rt.id: rt.code}, {rp.id: rp.code}, None),
            )
        )
    return detail


@router.post("/quotes", response_model=PriceOut, responses=ERRORS)
def quote(body: StayIn, db: DbSession, now: Now, rules: Rules) -> PriceOut:
    """Price a whole selection, with an optional promo code, without reserving anything."""
    request = to_request(db, body)
    result = quote_stay(db, request, now=now, rules=rules, promo_code=body.promo_code)
    codes = {rt.id: rt.code for rt in db.scalars(select(RoomType))}
    plan_codes = {rp.id: rp.code for rp in db.scalars(select(RatePlan))}
    return price_out(result.price, request, codes, plan_codes, result.promo)
