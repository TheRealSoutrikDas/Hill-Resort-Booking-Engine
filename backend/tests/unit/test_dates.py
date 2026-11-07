from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.dates import business_today, stay_nights, validate_stay
from app.services.errors import InvalidStay

IST = ZoneInfo("Asia/Kolkata")
TODAY = date(2026, 11, 7)
RULES = dict(today=TODAY, horizon_days=180, max_nights=14)


def test_check_out_is_exclusive() -> None:
    assert stay_nights(date(2026, 11, 14), date(2026, 11, 16)) == [
        date(2026, 11, 14),
        date(2026, 11, 15),
    ]


def test_stay_across_year_end() -> None:
    nights = stay_nights(date(2026, 12, 30), date(2027, 1, 2))
    assert nights == [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1)]


@pytest.mark.parametrize("check_out", [date(2026, 11, 14), date(2026, 11, 13)])
def test_check_out_must_be_after_check_in(check_out: date) -> None:
    with pytest.raises(InvalidStay) as err:
        stay_nights(date(2026, 11, 14), check_out)
    assert err.value.code == "check_out_not_after_check_in"


def test_business_today_uses_ist_not_utc() -> None:
    # 18:45 UTC on 7 Nov is 00:15 IST on 8 Nov.
    assert business_today(datetime(2026, 11, 7, 18, 45, tzinfo=UTC), IST) == date(2026, 11, 8)
    assert business_today(datetime(2026, 11, 7, 18, 15, tzinfo=UTC), IST) == date(2026, 11, 7)


def test_business_today_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        business_today(datetime(2026, 11, 7, 10, 0), IST)


def test_same_day_check_in_is_allowed() -> None:
    assert validate_stay(TODAY, TODAY + timedelta(days=1), **RULES) == [TODAY]


def test_check_in_in_the_past_is_rejected() -> None:
    with pytest.raises(InvalidStay) as err:
        validate_stay(TODAY - timedelta(days=1), TODAY + timedelta(days=1), **RULES)
    assert err.value.code == "check_in_in_past"


def test_booking_window_is_180_days_including_today() -> None:
    last = TODAY + timedelta(days=179)
    assert validate_stay(last, last + timedelta(days=1), **RULES) == [last]
    with pytest.raises(InvalidStay) as err:
        validate_stay(last + timedelta(days=1), last + timedelta(days=2), **RULES)
    assert err.value.code == "check_in_beyond_horizon"


def test_maximum_stay_is_14_nights() -> None:
    assert len(validate_stay(TODAY, TODAY + timedelta(days=14), **RULES)) == 14
    with pytest.raises(InvalidStay) as err:
        validate_stay(TODAY, TODAY + timedelta(days=15), **RULES)
    assert err.value.code == "stay_too_long"
