"""Request and response models shared by the booking routes.

The API speaks in codes (`DLX`, `RO`), never database ids (A-84), and in integer paise
(A-89); the frontend formats rupees.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.models import PromoCode
from app.services.errors import InvalidBookingRequest
from app.services.pricing import StayPrice
from app.services.quotes import HoldLineRequest, HoldRequest
from app.services.rates import rate_plans_by_code, room_types_by_code


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_type: str = Field(min_length=1, max_length=32, examples=["DLX"])
    rate_plan: str = Field(min_length=1, max_length=32, examples=["RO"])
    units: int = Field(ge=1, le=20)
    guests: int = Field(ge=1, le=100)


class StayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_in: date
    check_out: date
    lines: list[LineIn] = Field(min_length=1, max_length=10)
    promo_code: str | None = Field(default=None, max_length=32)


class NightOut(BaseModel):
    date: date
    rate_paise: int
    discount_paise: int
    taxable_paise: int
    gst_rate_bp: int  # 500 = 5%
    gst_paise: int


class LineOut(BaseModel):
    room_type: str
    rate_plan: str
    units: int
    guests: int
    nights: list[NightOut]  # per room
    subtotal_paise: int  # all rooms of this line
    discount_paise: int
    gst_paise: int
    total_paise: int


class PromoOut(BaseModel):
    code: str
    percent_off: int


class PriceOut(BaseModel):
    lines: list[LineOut]
    subtotal_paise: int
    discount_paise: int
    gst_paise: int
    total_paise: int
    promo: PromoOut | None = None


def to_request(db: Session, body: StayIn) -> HoldRequest:
    """Turn codes into the ids the services use; unknown codes use the services' codes."""
    room_types = room_types_by_code(db, (line.room_type for line in body.lines))
    rate_plans = rate_plans_by_code(db, (line.rate_plan for line in body.lines))
    lines = []
    for line in body.lines:
        room_type = room_types.get(line.room_type.strip().upper())
        if room_type is None:
            raise InvalidBookingRequest("unknown_room_type", "That room type does not exist.")
        rate_plan = rate_plans.get(line.rate_plan.strip().upper())
        if rate_plan is None:
            raise InvalidBookingRequest("unknown_rate_plan", "That rate plan does not exist.")
        lines.append(HoldLineRequest(room_type.id, rate_plan.id, line.units, line.guests))
    return HoldRequest(body.check_in, body.check_out, lines)


def price_out(
    price: StayPrice,
    request: HoldRequest,
    codes: dict[int, str],
    plan_codes: dict[int, str],
    promo: PromoCode | None,
) -> PriceOut:
    return PriceOut(
        lines=[
            LineOut(
                room_type=codes[req.room_type_id],
                rate_plan=plan_codes[req.rate_plan_id],
                units=req.units,
                guests=req.guests,
                nights=[
                    NightOut(
                        date=n.stay_date,
                        rate_paise=n.rate_paise,
                        discount_paise=n.discount_paise,
                        taxable_paise=n.taxable_paise,
                        gst_rate_bp=n.tax_rate_bp,
                        gst_paise=n.tax_paise,
                    )
                    for n in line.nights
                ],
                subtotal_paise=line.subtotal_paise,
                discount_paise=line.discount_paise,
                gst_paise=line.tax_paise,
                total_paise=line.total_paise,
            )
            for req, line in zip(request.lines, price.lines, strict=True)
        ],
        subtotal_paise=price.subtotal_paise,
        discount_paise=price.discount_paise,
        gst_paise=price.tax_paise,
        total_paise=price.total_paise,
        promo=PromoOut(code=promo.code, percent_off=promo.percent_off) if promo else None,
    )
