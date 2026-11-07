"""Price a stay without reserving anything: the room page's "price with GST" (D-30).

`create_hold` calls `quote_stay` too, so the price a guest is shown and the price that
is held come from one code path and cannot drift apart. A quote takes no locks, writes
nothing and does not check stock (availability is shown separately).
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PromoCode
from app.services.dates import business_today, validate_stay
from app.services.errors import InvalidBookingRequest
from app.services.pricing import GstRule, LineInput, StayPrice, price_stay
from app.services.promos import find_promo
from app.services.rates import load_nightly_rates, load_rate_plans, load_room_types


@dataclass(frozen=True)
class HoldRules:
    """The booking rules quotes and holds need, so tests can set them without
    environment variables."""

    tz: ZoneInfo
    horizon_days: int
    max_nights: int
    max_units: int
    ttl_minutes: int
    lock_timeout_ms: int
    gst_rule: GstRule

    @classmethod
    def from_settings(cls, settings: Settings) -> "HoldRules":
        return cls(
            tz=ZoneInfo(settings.business_timezone),
            horizon_days=settings.booking_horizon_days,
            max_nights=settings.max_stay_nights,
            max_units=settings.max_units_per_booking,
            ttl_minutes=settings.hold_ttl_minutes,
            lock_timeout_ms=settings.lock_timeout_ms,
            gst_rule=GstRule.from_settings(settings),
        )


@dataclass(frozen=True)
class HoldLineRequest:
    room_type_id: int
    rate_plan_id: int
    units: int
    guests: int


@dataclass(frozen=True)
class HoldRequest:
    check_in: date
    check_out: date
    lines: Sequence[HoldLineRequest]


@dataclass(frozen=True)
class Quote:
    nights: tuple[date, ...]
    price: StayPrice  # per line and per night, each night with its GST rate
    promo: PromoCode | None


def _validate_lines(lines: Sequence[HoldLineRequest], max_units: int) -> None:
    """Checks that need no database, so bad requests never reach a lookup or a lock."""
    if not lines:
        raise InvalidBookingRequest("no_lines", "Choose at least one room.")
    for line in lines:
        if line.units <= 0:
            raise InvalidBookingRequest("invalid_units", "Each room line needs at least one room.")
        if line.guests < line.units:
            raise InvalidBookingRequest("too_few_guests", "Each room needs at least one guest.")
    pairs = Counter((line.room_type_id, line.rate_plan_id) for line in lines)
    if any(count > 1 for count in pairs.values()):
        raise InvalidBookingRequest(
            "duplicate_line", "Combine rooms of the same type and plan into one line."
        )
    if sum(line.units for line in lines) > max_units:
        raise InvalidBookingRequest(
            "too_many_units",
            f"Online bookings are up to {max_units} rooms. Please send us an enquiry.",
        )


def quote_stay(
    session: Session,
    request: HoldRequest,
    *,
    now: datetime,
    rules: HoldRules,
    promo_code: str | None = None,
) -> Quote:
    """Validate a stay request and price it, optionally with a promo code.

    Raises InvalidStay, InvalidBookingRequest or InvalidPromoCode with a stable code.
    """
    today = business_today(now, rules.tz)
    nights = validate_stay(
        request.check_in,
        request.check_out,
        today=today,
        horizon_days=rules.horizon_days,
        max_nights=rules.max_nights,
    )
    _validate_lines(request.lines, rules.max_units)

    room_types = load_room_types(session, (line.room_type_id for line in request.lines))
    rate_plans = load_rate_plans(session, (line.rate_plan_id for line in request.lines))
    for line in request.lines:
        room_type = room_types.get(line.room_type_id)
        if room_type is None:
            raise InvalidBookingRequest("unknown_room_type", "That room type does not exist.")
        if line.guests > line.units * room_type.max_guests:
            raise InvalidBookingRequest(
                "too_many_guests",
                f"{room_type.name} takes up to {room_type.max_guests} guests per room.",
            )
        rate_plan = rate_plans.get(line.rate_plan_id)
        if rate_plan is None:
            raise InvalidBookingRequest("unknown_rate_plan", "That rate plan does not exist.")
        if not rate_plan.is_active:
            raise InvalidBookingRequest("rate_plan_inactive", f"{rate_plan.name} is not on sale.")

    rates = load_nightly_rates(
        session, ((line.room_type_id, line.rate_plan_id) for line in request.lines), nights
    )
    line_inputs = []
    for line in request.lines:
        nightly = {n: rates.get((line.room_type_id, line.rate_plan_id, n)) for n in nights}
        if any(price is None for price in nightly.values()):
            raise InvalidBookingRequest(
                "rate_unavailable", "These dates are not on sale for this room and plan."
            )
        line_inputs.append(LineInput(nightly, line.units))

    promo = find_promo(session, promo_code, today=today, now=now) if promo_code else None
    price = price_stay(line_inputs, promo.percent_off if promo else 0, rules.gst_rule)
    return Quote(nights=tuple(nights), price=price, promo=promo)
