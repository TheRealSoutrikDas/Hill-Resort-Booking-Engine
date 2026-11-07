import csv
import io
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.exports import COLUMNS, day_bounds, neutralise, to_csv

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize("value", ['=HYPERLINK("x")', "+cmd", "-2+3", "@SUM(A1)", "\tx", "\rx"])
def test_formula_starts_are_neutralised(value: str) -> None:
    assert neutralise(value) == "'" + value


@pytest.mark.parametrize("value", ["Asha Rao", "asha@example.com", "O'Neil", ""])
def test_ordinary_text_is_untouched(value: str) -> None:
    assert neutralise(value) == value


def test_ist_day_bounds_in_utc() -> None:
    start, end = day_bounds(date(2026, 11, 8), IST)
    assert start == datetime(2026, 11, 7, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 11, 8, 18, 30, tzinfo=UTC)


def test_csv_has_the_header_and_quotes_commas_and_quotes() -> None:
    row = dict.fromkeys(COLUMNS, "")
    row.update(guest_name='Rao, "Asha"', line_number=1)
    text = to_csv([row])
    assert text.startswith(",".join(COLUMNS) + "\r\n")
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert parsed[0]["guest_name"] == 'Rao, "Asha"'


def test_empty_day_is_just_the_header() -> None:
    assert to_csv([]) == ",".join(COLUMNS) + "\r\n"
