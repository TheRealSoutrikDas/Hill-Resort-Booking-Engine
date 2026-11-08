"""Rule-based field extraction (A-108, A-112, A-113)."""

from datetime import date

import pytest

from app.classifiers.extract import extract_fields
from app.classifiers.fields import ExtractedFields, keep_plausible

THU = date(2026, 11, 5)  # the samples' received_on, a Thursday


def fields(message: str, received_on: date = THU) -> dict:
    return extract_fields(message, received_on).model_dump(exclude_none=True)


@pytest.mark.parametrize(
    ("message", "check_in", "check_out"),
    [
        ("Is a villa free 14-16 Nov?", "2026-11-14", "2026-11-16"),
        ("pls tell rates for deluxe room nov 28-30", "2026-11-28", "2026-11-30"),
        ("family suite Dec 26 to Jan 1", "2026-12-26", "2027-01-01"),  # crosses the year
        ("workshop March 10-13", "2027-03-10", "2027-03-13"),  # March has passed this year
        ("villa chahiye 24 se 26 December", "2026-12-24", "2026-12-26"),
        ("20 दिसंबर से 22 दिसंबर तक कमरा", "2026-12-20", "2026-12-22"),
        ("ಡಿಸೆಂಬರ್ 24 ರಿಂದ 26 ರವರೆಗೆ ಕೋಣೆ", "2026-12-24", "2026-12-26"),
        ("Need rooms 3rd-5th Jan 2028", "2028-01-03", "2028-01-05"),
    ],
)
def test_date_ranges(message: str, check_in: str, check_out: str) -> None:
    got = fields(message)
    assert (str(got["check_in"]), str(got["check_out"])) == (check_in, check_out)


@pytest.mark.parametrize(
    ("message", "check_in"),
    [
        ("price for the Estate View room on 31 Dec?", "2026-12-31"),
        ("Engagement function, 12 Jan", "2027-01-12"),
        ("a room this Saturday for a couple", "2026-11-07"),
        ("a room next Thursday", "2026-11-12"),  # "next" on the same weekday is a week on
        ("a room tomorrow", "2026-11-06"),
        ("Dec 31 please", "2026-12-31"),
    ],
)
def test_single_dates(message: str, check_in: str) -> None:
    got = fields(message)
    assert str(got["check_in"]) == check_in and "check_out" not in got


@pytest.mark.parametrize(
    ("message", "event_month"),
    [
        ("wedding in Feb 2027", "2027-02"),
        ("Team of 45 wants a January offsite", "2027-01"),
        ("first week of February", "2027-02"),
        ("Reception in March", "2027-03"),
        ("Engagement function, 12 Jan", "2027-01"),  # from the date when no bare month
        ("we may come in December", "2026-12"),  # "may" the verb is not May
    ],
)
def test_event_month(message: str, event_month: str) -> None:
    assert fields(message)["event_month"] == event_month


@pytest.mark.parametrize(
    ("message", "guests"),
    [
        ("2 adults and a child", 3),
        ("2 adults 2 kids", 4),
        ("Need 2 rooms for 4 adults", 4),
        ("Team of 45", 45),
        ("30 pax, 3 nights", 30),
        ("about 250 guests", 250),
        ("for a couple", 2),
        ("3 logon ke liye villa", 3),
        ("2 लोगों के लिए", 2),
        ("2 ಜನರಿಗೆ ಕೋಣೆ", 2),
        ("quote a villa for 2 on 5-7 Jan", 2),
        ("around 150 guests, rooms for 60", 150),  # people beat the room count
    ],
)
def test_guests(message: str, guests: int) -> None:
    assert fields(message)["guests"] == guests


@pytest.mark.parametrize(
    ("message", "budget"),
    [
        ("Budget 8000 per night", 8_000),  # stored as stated (A-112)
        ("Budget around 1.5 lakh total", 150_000),
        ("Budget 25 lakh.", 2_500_000),
        ("budget of ₹1,20,000", 120_000),
        ("budget 2 crore", 20_000_000),
    ],
)
def test_budget(message: str, budget: int) -> None:
    assert fields(message)["budget_inr"] == budget


def test_nights_stated_or_derived() -> None:
    assert fields("2 day leadership retreat")["nights"] == 2
    assert fields("2 nights in Feb")["nights"] == 2
    assert fields("villa 14-16 Nov")["nights"] == 2  # derived from the range


@pytest.mark.parametrize(
    ("message", "room_type"),
    [
        ("pool villa", "PPV"),
        ("a villa", "PLV"),
        ("family suite", "FST"),
        ("Estate View room", "EVR"),
        ("deluxe", "DLX"),
    ],
)
def test_room_type_hint(message: str, room_type: str) -> None:
    assert fields(message)["room_type"] == room_type


def test_nothing_recognised_stays_empty() -> None:
    assert fields("hi") == {}
    assert fields("Can I have the 30th of Febtober?") == {}


def test_impossible_dates_are_dropped_not_guessed() -> None:
    assert "check_in" not in fields("a room on 30 Feb")


def test_known_limit_new_years_eve_is_not_understood() -> None:
    # Recorded, not hidden: such phrasings leave dates empty and rely on the LLM.
    assert "check_in" not in fields("Any rooms for New Year's Eve?")


# ---------- the fields model checks values (shared with the LLM in step 22) ----------


@pytest.mark.parametrize(
    "bad",
    [
        {"check_in": "2026-12-10", "check_out": "2026-12-09"},
        {"guests": 0},
        {"guests": 5000},
        {"nights": 0},
        {"budget_inr": -5},
        {"event_month": "2027-13"},
        {"room_type": "dlx"},
        {"unexpected": 1},
    ],
)
def test_fields_model_rejects_impossible_values(bad: dict) -> None:
    with pytest.raises(ValueError):
        ExtractedFields(**bad)


def test_implausible_dates_are_dropped() -> None:
    far = ExtractedFields(
        check_in=date(2031, 1, 1), check_out=date(2031, 1, 3), event_month="2031-01"
    )
    assert keep_plausible(far, THU).model_dump(exclude_none=True) == {}
    past = ExtractedFields(check_in=date(2026, 10, 1))
    assert keep_plausible(past, THU).check_in is None
    yesterday = ExtractedFields(check_in=date(2026, 11, 4))
    assert keep_plausible(yesterday, THU).check_in == date(2026, 11, 4)


def test_check_out_is_dropped_when_its_check_in_is() -> None:
    # Check-in is in the past, check-out is fine: a lone check-out means nothing.
    stale = ExtractedFields(check_in=date(2026, 10, 1), check_out=date(2026, 11, 10))
    assert keep_plausible(stale, THU).model_dump(exclude_none=True) == {}
