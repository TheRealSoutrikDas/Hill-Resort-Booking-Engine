"""Stay dates in the business timezone.

Check-in is inclusive and check-out exclusive: a 14 to 16 Nov stay is the nights of
14 and 15 Nov. Dates are plain `date` values; "today" is the business date (IST).
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.errors import InvalidStay


def business_today(now: datetime, tz: ZoneInfo) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(tz).date()


def stay_nights(check_in: date, check_out: date) -> list[date]:
    if check_out <= check_in:
        raise InvalidStay("check_out_not_after_check_in", "Check-out must be after check-in.")
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


def validate_stay(
    check_in: date,
    check_out: date,
    *,
    today: date,
    horizon_days: int,
    max_nights: int,
) -> list[date]:
    """Apply the booking rules (A-38 to A-40) and return the nights of the stay."""
    nights = stay_nights(check_in, check_out)
    if check_in < today:
        raise InvalidStay("check_in_in_past", "Check-in cannot be in the past.")
    last_check_in = today + timedelta(days=horizon_days - 1)
    if check_in > last_check_in:
        raise InvalidStay(
            "check_in_beyond_horizon",
            f"Bookings open up to {last_check_in.isoformat()}.",
        )
    if len(nights) > max_nights:
        raise InvalidStay(
            "stay_too_long",
            f"Online bookings are up to {max_nights} nights. Please send us an enquiry.",
        )
    return nights
