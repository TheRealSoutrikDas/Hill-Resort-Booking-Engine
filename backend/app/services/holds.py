"""Phase 1 of a booking: hold stock (and a promo use) for a signed-in guest and fix the price.

A hold reserves units on every night of the stay for `hold_ttl_minutes` and stores the
exact per-night prices the guest saw (A-45). It never changes `allotments.sold`; only
converting it into a booking does (step 6). Expired holds are ignored, not deleted.

Every hold belongs to the account that created it (A-43). Only that account can add
guest details to it or release it; for anyone else it does not exist (HoldNotFound).

Functions take a Session and never commit: the caller commits, which also releases the
stock locks taken by `create_hold`.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Hold, HoldItem, HoldItemNight
from app.db.models.enums import HoldStatus
from app.services.availability import StockRequest, lock_and_check
from app.services.errors import HoldNotActive, HoldNotFound, InvalidBookingRequest
from app.services.pricing import StayPrice
from app.services.promos import reserve_use
from app.services.quotes import HoldLineRequest, HoldRequest, HoldRules, quote_stay

# The request and rules types live with the quote; re-exported for callers of holds.
__all__ = [
    "HoldLineRequest",
    "HoldRequest",
    "HoldResult",
    "HoldRules",
    "create_hold",
    "get_owned_hold",
    "release_hold",
    "require_active",
    "set_guest_details",
]


@dataclass(frozen=True)
class HoldResult:
    hold_id: UUID
    expires_at: datetime
    price: StayPrice


# ---------- create ----------


def create_hold(
    session: Session,
    user_id: int,
    request: HoldRequest,
    *,
    now: datetime,
    rules: HoldRules,
    promo_code: str | None = None,
) -> HoldResult:
    """Quote, then check stock and the promo code under lock, then write the hold.
    All or nothing: if any line is short on any night, nothing is written (NotAvailable);
    if the code's last use is taken, nothing is written (InvalidPromoCode)."""
    # Validation, catalogue checks and price: the same code path as the room page.
    quote = quote_stay(session, request, now=now, rules=rules, promo_code=promo_code)

    # The only locked part, in the shared order: allotment rows, then the promo row.
    lock_and_check(
        session,
        [StockRequest(line.room_type_id, line.units) for line in request.lines],
        list(quote.nights),
        now,
        rules.lock_timeout_ms,
    )
    if quote.promo is not None:
        reserve_use(session, quote.promo.id, now=now, lock_timeout_ms=rules.lock_timeout_ms)

    price = quote.price
    hold = Hold(
        user_id=user_id,
        check_in=request.check_in,
        check_out=request.check_out,
        promo_code_id=quote.promo.id if quote.promo else None,
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
