"""Fill a draft reply's placeholders in code (brief; A-118, D-42).

Prices come from `quote_stay`, the same path as the website, never from model text and
never with a promo, so a message asking for a discount cannot change a price. A value
that cannot be worked out leaves its placeholder visible for staff, never a guess.
"""

import math
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classifiers.fields import ExtractedFields
from app.db.models import RatePlan, RoomType
from app.services.availability import stay_availability
from app.services.dates import stay_nights
from app.services.errors import DomainError
from app.services.quotes import HoldLineRequest, HoldRequest, HoldRules, quote_stay

DRAFT_RATE_PLAN = "RO"  # drafts quote Room Only (A-118)
NOT_AVAILABLE = "not available on these dates, so we will suggest alternatives"


def format_inr(paise: int) -> str:
    """Indian digit grouping: 150000000 paise -> 'Rs 15,00,000'."""
    rupees, rest = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return f"Rs {digits}" + (f".{rest:02d}" if rest else "")


def format_dates(check_in: date, check_out: date) -> str:
    return f"{check_in.day} {check_in:%b %Y} to {check_out.day} {check_out:%b %Y}"


def format_month(event_month: str) -> str:
    year, month = (int(p) for p in event_month.split("-"))
    return f"{date(year, month, 1):%B %Y}"


def stay_dates(fields: ExtractedFields) -> tuple[date | None, date | None]:
    """Check-in and check-out, inferring check-out from nights when only that is given."""
    check_out = fields.check_out
    if fields.check_in and check_out is None and fields.nights:
        check_out = fields.check_in + timedelta(days=fields.nights)
    return fields.check_in, check_out


def _price(
    session: Session,
    room: RoomType,
    check_in: date,
    check_out: date,
    guests: int,
    *,
    now: datetime,
    rules: HoldRules,
) -> str | None:
    units = math.ceil(guests / room.max_guests)
    if units > rules.max_units:
        return None  # a group: staff will quote
    plan = session.scalar(select(RatePlan).where(RatePlan.code == DRAFT_RATE_PLAN))
    if plan is None:
        return None
    request = HoldRequest(check_in, check_out, [HoldLineRequest(room.id, plan.id, units, guests)])
    try:
        quote = quote_stay(session, request, now=now, rules=rules)  # never a promo code
        available = stay_availability(session, [room.id], stay_nights(check_in, check_out), now)[
            room.id
        ]
    except DomainError:
        return None  # dates out of the window, no rate: staff will fill it in
    if available < units:
        return NOT_AVAILABLE
    rooms = f" for {units} rooms" if units > 1 else ""
    return f"{format_inr(quote.price.total_paise)}{rooms}"


def build_draft(
    session: Session,
    template: str,
    fields: ExtractedFields,
    contact_name: str | None,
    *,
    now: datetime,
    rules: HoldRules,
) -> str:
    values: dict[str, str] = {}
    check_in, check_out = stay_dates(fields)
    if check_in and check_out:
        values["dates"] = format_dates(check_in, check_out)
    if fields.guests:
        values["guests"] = str(fields.guests)
    if fields.event_month:
        values["event_month"] = format_month(fields.event_month)
    room = None
    if fields.room_type:
        room = session.scalar(select(RoomType).where(RoomType.code == fields.room_type))
        if room is not None:
            values["room_type"] = room.name
    if room and check_in and check_out and fields.guests:
        if (
            price := _price(session, room, check_in, check_out, fields.guests, now=now, rules=rules)
        ) is not None:
            values["price_total"] = price

    draft = template
    for key, value in values.items():
        draft = draft.replace("{" + key + "}", value)
    # The name goes in last, so a name that looks like a placeholder is never filled.
    return draft.replace("{guest_name}", (contact_name or "").strip() or "Guest")
