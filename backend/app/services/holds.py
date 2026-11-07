"""Phase 1 of a booking: hold stock for a signed-in guest and fix the price.

A hold reserves units on every night of the stay for `hold_ttl_minutes` and stores the
exact per-night prices the guest saw (A-45). It never changes `allotments.sold`; only
converting it into a booking does (step 6). Expired holds are ignored, not deleted.

Every hold belongs to the account that created it (A-43). Only that account can add
guest details to it or release it; for anyone else it does not exist (HoldNotFound).

Functions take a Session and never commit: the caller commits, which also releases the
stock locks taken by `create_hold`.
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Hold, HoldItem, HoldItemNight
from app.db.models.enums import HoldStatus
from app.services.availability import StockRequest, lock_and_check
from app.services.dates import business_today, validate_stay
from app.services.errors import HoldNotActive, HoldNotFound, InvalidBookingRequest
from app.services.pricing import GstRule, LineInput, StayPrice, price_stay
from app.services.rates import load_nightly_rates, load_rate_plans, load_room_types


@dataclass(frozen=True)
class HoldRules:
    """The booking rules a hold needs, so tests can set them without environment variables."""

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
class HoldResult:
    hold_id: UUID
    expires_at: datetime
    price: StayPrice


# ---------- create ----------


def _validate_lines(lines: Sequence[HoldLineRequest], max_units: int) -> None:
    """Checks that need no database, so bad requests never take a lock."""
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


def create_hold(
    session: Session,
    user_id: int,
    request: HoldRequest,
    *,
    now: datetime,
    rules: HoldRules,
) -> HoldResult:
    """Validate, check stock under lock, price, and write the hold. All or nothing:
    if any line is short on any night, nothing is written (NotAvailable)."""
    nights = validate_stay(
        request.check_in,
        request.check_out,
        today=business_today(now, rules.tz),
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

    # The only locked part: check stock, then write. Locks are held until commit.
    lock_and_check(
        session,
        [StockRequest(line.room_type_id, line.units) for line in request.lines],
        nights,
        now,
        rules.lock_timeout_ms,
    )
    price = price_stay(line_inputs, 0, rules.gst_rule)  # promo codes join in step 9 (A-47)

    hold = Hold(
        user_id=user_id,
        check_in=request.check_in,
        check_out=request.check_out,
        subtotal_paise=price.subtotal_paise,
        discount_paise=price.discount_paise,
        tax_paise=price.tax_paise,
        total_paise=price.total_paise,
        status=HoldStatus.ACTIVE,
        expires_at=now + timedelta(minutes=rules.ttl_minutes),
        created_at=now,
    )
    for line_number, (line, priced) in enumerate(
        zip(request.lines, price.lines, strict=True), start=1
    ):
        hold.items.append(
            HoldItem(
                line_number=line_number,
                room_type_id=line.room_type_id,
                rate_plan_id=line.rate_plan_id,
                units=line.units,
                guests=line.guests,
                subtotal_paise=priced.subtotal_paise,
                discount_paise=priced.discount_paise,
                tax_paise=priced.tax_paise,
                nights=[
                    HoldItemNight(
                        stay_date=night.stay_date,
                        rate_paise=night.rate_paise,
                        discount_paise=night.discount_paise,
                        tax_paise=night.tax_paise,
                        tax_rate_bp=night.tax_rate_bp,
                    )
                    for night in priced.nights
                ],
            )
        )
    session.add(hold)
    session.flush()
    return HoldResult(hold_id=hold.id, expires_at=hold.expires_at, price=price)


# ---------- ownership and state ----------


def get_owned_hold(session: Session, user_id: int, hold_id: UUID, *, lock: bool = False) -> Hold:
    """The hold, if it belongs to this account. `lock` takes a row lock on the hold so
    two requests for the same hold (a double click) run one after the other."""
    stmt = select(Hold).where(Hold.id == hold_id, Hold.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    hold = session.scalar(stmt)
    if hold is None:
        raise HoldNotFound("Hold not found.")
    return hold


def require_active(hold: Hold, now: datetime) -> None:
    if hold.status == HoldStatus.CONVERTED:
        raise HoldNotActive("hold_converted", "This booking is already paid.")
    if hold.status == HoldStatus.RELEASED:
        raise HoldNotActive("hold_released", "This selection was cancelled. Please start again.")
    if hold.expires_at <= now:
        raise HoldNotActive(
            "hold_expired", "Your rooms were held for 10 minutes. Please start again."
        )


# ---------- guest details ----------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 ]{6,18}[0-9]$")


def set_guest_details(
    session: Session,
    user_id: int,
    hold_id: UUID,
    *,
    name: str,
    email: str,
    phone: str,
    now: datetime,
) -> Hold:
    """Booking step 2: who is staying. Prefilled from the account by the frontend, but the
    guest may name someone else, for example when booking for family (A-43)."""
    name, email, phone = name.strip(), email.strip().lower(), " ".join(phone.split())
    if not 1 <= len(name) <= 120:
        raise InvalidBookingRequest("invalid_guest_name", "Enter the guest's name.")
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        raise InvalidBookingRequest("invalid_guest_email", "Enter a valid email address.")
    if len(phone) > 20 or not _PHONE_RE.fullmatch(phone):
        raise InvalidBookingRequest("invalid_guest_phone", "Enter a valid phone number.")

    hold = get_owned_hold(session, user_id, hold_id, lock=True)
    require_active(hold, now)
    hold.guest_name, hold.guest_email, hold.guest_phone = name, email, phone
    session.flush()
    return hold


# ---------- release ----------


def release_hold(session: Session, user_id: int, hold_id: UUID) -> Hold:
    """The guest went back or changed rooms: free the stock now instead of at expiry
    (A-44). Releasing twice is harmless; a paid hold cannot be released.

    Release only frees stock, so it needs the hold row lock but not the allotment locks:
    a check that runs at the same moment can at worst see slightly less stock than
    there is, never more."""
    hold = get_owned_hold(session, user_id, hold_id, lock=True)
    if hold.status == HoldStatus.CONVERTED:
        raise HoldNotActive("hold_converted", "This booking is already paid.")
    if hold.status == HoldStatus.ACTIVE:
        hold.status = HoldStatus.RELEASED
        session.flush()
    return hold
