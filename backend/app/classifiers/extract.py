"""Rule-based field extraction from an enquiry (A-108, D-41).

Pulls dates, guests, nights, budget and a room type hint out of the message, resolved
against the day it was received (IST). Written around the phrasings in the sample
enquiries, in English, Hinglish, Hindi and Kannada. Anything it does not recognise is
left empty, never guessed; such enquiries go to Unsorted or rely on the LLM.

A date without a year is its next occurrence on or after the day received; in a range,
a check-out that would fall before check-in moves to the next year (Dec 26 to Jan 1).
"""

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.classifiers.fields import ExtractedFields, keep_plausible

# ---------- month names ----------

_MONTH_NAMES: dict[str, int] = {}
for number, names in enumerate(
    [
        ("january", "jan", "जनवरी", "ಜನವರಿ"),
        ("february", "feb", "फरवरी", "फ़रवरी", "ಫೆಬ್ರವರಿ"),
        ("march", "mar", "मार्च", "ಮಾರ್ಚ್"),
        ("april", "apr", "अप्रैल", "ಏಪ್ರಿಲ್"),
        ("may", "मई", "ಮೇ"),
        ("june", "jun", "जून", "ಜೂನ್"),
        ("july", "jul", "जुलाई", "ಜುಲೈ"),
        ("august", "aug", "अगस्त", "ಆಗಸ್ಟ್"),
        ("september", "sept", "sep", "सितंबर", "सितम्बर", "ಸೆಪ್ಟೆಂಬರ್"),
        ("october", "oct", "अक्टूबर", "ಅಕ್ಟೋಬರ್"),
        ("november", "nov", "नवंबर", "नवम्बर", "ನವೆಂಬರ್"),
        ("december", "dec", "दिसंबर", "दिसम्बर", "ಡಿಸೆಂಬರ್"),
    ],
    start=1,
):
    for name in names:
        _MONTH_NAMES[name] = number

_MONTH_ALT = "|".join(sorted(map(re.escape, _MONTH_NAMES), key=len, reverse=True))


def _mon(group: str) -> str:
    # Latin month names need word edges ("mar" must not match "market").
    return rf"(?<![a-z])(?P<{group}>{_MONTH_ALT})(?![a-z])"


def _day(group: str) -> str:
    return rf"(?<!\d)(?P<{group}>\d{{1,2}})(?:st|nd|rd|th)?(?!\d)"


_SEP = r"\s*(?:-|\u2013|\u2014|to|till|until|se|से|ರಿಂದ)\s*"
_YEAR = r"(?:\s*,?\s*(?P<year>20\d{2}))?"

# 14-16 Nov | 24 se 26 December | 20 दिसंबर से 22 दिसंबर
_RANGE_DAY_FIRST = re.compile(
    rf"{_day('d1')}\s*(?:{_mon('m1')})?{_SEP}{_day('d2')}\s*{_mon('m2')}{_YEAR}"
)
# Dec 26 to Jan 1 | nov 28-30 | March 10-13 | ಡಿಸೆಂಬರ್ 24 ರಿಂದ 26
_RANGE_MONTH_FIRST = re.compile(
    rf"{_mon('m1')}\s*{_day('d1')}{_SEP}(?:{_mon('m2')}\s*)?{_day('d2')}{_YEAR}"
)
# 31 Dec | 12 Jan 2027
_SINGLE_DAY_FIRST = re.compile(rf"{_day('d1')}\s*{_mon('m1')}{_YEAR}")
# Dec 31
_SINGLE_MONTH_FIRST = re.compile(rf"{_mon('m1')}\s*{_day('d1')}{_YEAR}")
# Feb 2027 | in March | January offsite
_BARE_MONTH = re.compile(rf"{_mon('m1')}(?:\s*,?\s*(?P<year>20\d{{2}}))?")

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_RELATIVE = re.compile(
    rf"\b(?P<which>this|next|coming)\s+(?P<day>{'|'.join(_WEEKDAYS)})\b|\b(?P<word>today|tomorrow)\b"
)


def _resolve(day: int, month: int, year: int | None, received_on: date) -> date | None:
    try:
        if year is not None:
            return date(year, month, day)
        candidate = date(received_on.year, month, day)
        return candidate if candidate >= received_on else date(received_on.year + 1, month, day)
    except ValueError:  # 30 Feb and the like
        return None


def _month_year(month: int, year: int | None, received_on: date) -> str:
    if year is None:
        year = received_on.year if month >= received_on.month else received_on.year + 1
    return f"{year:04d}-{month:02d}"


def _mask(text: str, match: re.Match) -> str:
    return text[: match.start()] + " " * (match.end() - match.start()) + text[match.end() :]


def extract_dates(text: str, received_on: date) -> tuple[date | None, date | None, str | None]:
    """(check_in, check_out, event_month) from lowercase text."""
    check_in = check_out = None
    ranges = [m for p in (_RANGE_DAY_FIRST, _RANGE_MONTH_FIRST) if (m := p.search(text))]
    if ranges:
        m = min(ranges, key=lambda r: r.start())
        year = int(m["year"]) if m["year"] else None
        m1 = _MONTH_NAMES[m["m1"]] if m["m1"] else _MONTH_NAMES[m["m2"]]
        m2 = _MONTH_NAMES[m["m2"]] if m["m2"] else m1
        check_in = _resolve(int(m["d1"]), m1, year, received_on)
        if check_in is not None:
            try:
                check_out = date(check_in.year, m2, int(m["d2"]))
                if check_out <= check_in:
                    check_out = date(check_in.year + 1, m2, int(m["d2"]))
            except ValueError:
                check_out = None
        text = _mask(text, m)
    else:
        singles = [m for p in (_SINGLE_DAY_FIRST, _SINGLE_MONTH_FIRST) if (m := p.search(text))]
        if singles:
            m = min(singles, key=lambda r: r.start())
            year = int(m["year"]) if m["year"] else None
            check_in = _resolve(int(m["d1"]), _MONTH_NAMES[m["m1"]], year, received_on)
            text = _mask(text, m)
        elif rel := _RELATIVE.search(text):
            if rel["word"]:
                check_in = received_on + timedelta(days=0 if rel["word"] == "today" else 1)
            else:
                target = _WEEKDAYS.index(rel["day"])
                ahead = (target - received_on.weekday()) % 7
                if rel["which"] == "next" and ahead == 0:
                    ahead = 7
                check_in = received_on + timedelta(days=ahead)

    event_month = None
    for m in _BARE_MONTH.finditer(text):
        if m["m1"] == "may" and not m["year"]:
            continue  # "may" is usually the verb
        event_month = _month_year(
            _MONTH_NAMES[m["m1"]], int(m["year"]) if m["year"] else None, received_on
        )
        break
    if event_month is None and check_in is not None:
        event_month = f"{check_in.year:04d}-{check_in.month:02d}"
    return check_in, check_out, event_month


# ---------- guests, nights, budget, room type ----------

_ADULTS = re.compile(r"(\d+)\s*adults?\b")
_KIDS = re.compile(r"(\d+)\s*(?:kids?|children|child)\b")
_ONE_KID = re.compile(r"\b(?:a|one)\s+(?:kid|child)\b")
_PEOPLE = re.compile(
    r"(?<!\d)(\d{1,4})\s*(?:people|persons?|guests?|pax|members|logon|log\b|लोगों|लोग|ಜನರಿಗೆ|ಜನರು|ಜನ)"
)
_TEAM = re.compile(r"\bteam\s+of\s+(\d{1,4})\b")
_COUPLE = re.compile(r"\bcouple\b")
_ROOM_FOR = re.compile(
    r"\b(?:villa|room|suite|cottage)s?\s+for\s+(\d{1,3})\b(?!\s*(?:nights?|days?))"
)
_NIGHTS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:nights?|days?)\b")
_BUDGET = re.compile(
    r"\bbudget\s*(?:of|is|around|about|approx\.?|approximately|~|:)?\s*(?:rs\.?|inr|₹)?\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>lakhs?|lacs?|l|k|crores?|cr)?\b"
)
_UNITS = {
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "l": 100_000,
    "k": 1_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}
_ROOM_HINTS = [
    ("pool villa", "PPV"),
    ("villa", "PLV"),
    ("family suite", "FST"),
    ("suite", "FST"),
    ("estate view", "EVR"),
    ("deluxe", "DLX"),
]


def extract_guests(text: str) -> int | None:
    if adults := _ADULTS.search(text):
        total = int(adults[1])
        if kids := _KIDS.search(text):
            total += int(kids[1])
        elif _ONE_KID.search(text):
            total += 1
        return total
    for pattern in (_PEOPLE, _TEAM):
        if m := pattern.search(text):
            return int(m[1])
    if _COUPLE.search(text):
        return 2
    if m := _ROOM_FOR.search(text):
        return int(m[1])
    return None


def extract_budget(text: str) -> int | None:
    if not (m := _BUDGET.search(text)):
        return None
    try:
        amount = Decimal(m["amount"].replace(",", ""))
    except InvalidOperation:
        return None
    return int(amount * _UNITS.get(m["unit"] or "", 1))


def extract_room_type(text: str) -> str | None:
    for phrase, code in _ROOM_HINTS:
        if re.search(rf"\b{phrase}s?\b", text):
            return code
    return None


def extract_fields(message: str, received_on: date) -> ExtractedFields:
    text = message.lower()
    check_in, check_out, event_month = extract_dates(text, received_on)
    nights = int(m[1]) if (m := _NIGHTS.search(text)) else None
    if nights is None and check_in and check_out:
        nights = (check_out - check_in).days
    guests = extract_guests(text)
    data = {
        "check_in": check_in,
        "check_out": check_out,
        "event_month": event_month,
        "guests": guests if guests and 1 <= guests <= 1_000 else None,
        "nights": nights if nights and 1 <= nights <= 60 else None,
        "budget_inr": extract_budget(text),
        "room_type": extract_room_type(text),
    }
    if data["check_in"] and data["check_out"] and data["check_out"] <= data["check_in"]:
        data["check_out"] = None
    return keep_plausible(ExtractedFields(**data), received_on)
