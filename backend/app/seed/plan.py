"""Every number the seed uses, in one place (A-09, confirmed by the client).

Dates are relative to "today" in the business timezone, so the demo always looks
current. The same today always produces the same data (fixed random seed).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.config import DEFAULT_MAX_UNITS_PER_BOOKING
from app.services.pricing import round_half_up_div

RANDOM_SEED = 42

# ---------- room types: 64 rooms + 12 villas = 76 keys ----------


@dataclass(frozen=True)
class RoomTypePlan:
    code: str
    name: str
    kind: str
    units: int
    max_guests: int
    weekday_rate_rupees: int
    description: str


ROOM_TYPES: tuple[RoomTypePlan, ...] = (
    RoomTypePlan(
        "DLX",
        "Deluxe Room",
        "room",
        30,
        3,
        6_000,
        "Queen bed, garden-facing balcony, coffee from the estate.",
    ),
    RoomTypePlan(
        "EVR",
        "Estate View Room",
        "room",
        22,
        3,
        8_000,
        "Upper-floor room looking over the coffee slopes.",
    ),
    RoomTypePlan(
        "FST",
        "Family Suite",
        "room",
        12,
        4,
        10_000,
        "Two connected rooms with a shared sitting area, for families.",
    ),
    RoomTypePlan(
        "PLV",
        "Plantation Villa",
        "villa",
        8,
        4,
        14_000,
        "Standalone villa among the coffee plants, with a private sit-out.",
    ),
    RoomTypePlan(
        "PPV", "Pool Villa", "villa", 4, 6, 20_500, "Two-bedroom villa with a private plunge pool."
    ),
)

# ---------- rate plans ----------

RATE_PLANS: tuple[tuple[str, str, str], ...] = (
    ("RO", "Room Only", "The room, without meals."),
    ("BB", "Bed and Breakfast", "The room with breakfast for the guests in it."),
)
BB_SUPPLEMENT_RUPEES = 1_200  # per room per night, on top of Room Only

# ---------- nightly rate rules ----------

WEEKEND_PERCENT = 120  # Friday and Saturday nights
PEAK_PERCENT = 140  # 20 Dec to 5 Jan, used instead of the weekend uplift
RATE_ROUND_TO_RUPEES = 100
RATES_DAYS_BEFORE_TODAY = 60
RATES_DAYS_AFTER_TODAY = 180


def is_peak(night: date) -> bool:
    return (night.month == 12 and night.day >= 20) or (night.month == 1 and night.day <= 5)


def is_weekend_night(night: date) -> bool:
    return night.weekday() in (4, 5)  # Friday, Saturday


def room_only_rate_rupees(weekday_rate_rupees: int, night: date) -> int:
    if is_peak(night):
        percent = PEAK_PERCENT
    elif is_weekend_night(night):
        percent = WEEKEND_PERCENT
    else:
        percent = 100
    steps = round_half_up_div(weekday_rate_rupees * percent, 100 * RATE_ROUND_TO_RUPEES)
    return steps * RATE_ROUND_TO_RUPEES


def rate_rupees(room_type: RoomTypePlan, rate_plan_code: str, night: date) -> int:
    rate = room_only_rate_rupees(room_type.weekday_rate_rupees, night)
    return rate + BB_SUPPLEMENT_RUPEES if rate_plan_code == "BB" else rate


# ---------- web allotment ----------

WEB_ALLOTMENT_PERCENT = 25


def web_allotment(units: int) -> int:
    return round_half_up_div(units * WEB_ALLOTMENT_PERCENT, 100)


# ---------- deliberate states ----------


def first_weekday_on_or_after(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


ONE_LEFT_LEAD_DAYS = 7  # Friday of the first weekend at least this far ahead
ONE_LEFT_ROOM_TYPE = "FST"  # 1 of 3 web units left on Friday and Saturday
SOLD_OUT_LEAD_DAYS = 14  # every room type sold out on Friday and Saturday
BLACKOUT_LEAD_DAYS = 35  # first Monday at least this far ahead
BLACKOUT_NIGHTS = 3


def one_left_friday(today: date) -> date:
    return first_weekday_on_or_after(today + timedelta(days=ONE_LEFT_LEAD_DAYS), 4)


def sold_out_friday(today: date) -> date:
    return first_weekday_on_or_after(today + timedelta(days=SOLD_OUT_LEAD_DAYS), 4)


def blackout_nights(today: date) -> list[date]:
    start = first_weekday_on_or_after(today + timedelta(days=BLACKOUT_LEAD_DAYS), 0)
    return [start + timedelta(days=i) for i in range(BLACKOUT_NIGHTS)]


# Bookings that exactly fill the sold-out weekend: (room type, units) per line.
# Web units per night: DLX 8, EVR 6, FST 3, PLV 2, PPV 1.
SOLD_OUT_BOOKINGS: tuple[tuple[tuple[str, int], ...], ...] = (
    (("DLX", 2),),
    (("DLX", 2),),
    (("DLX", 2),),
    (("DLX", 1), ("EVR", 1)),
    (("DLX", 1), ("FST", 1)),
    (("EVR", 2),),
    (("EVR", 2),),
    (("EVR", 1), ("PLV", 1)),
    (("FST", 2),),
    (("PLV", 1),),
    (("PPV", 1),),
)
ONE_LEFT_BOOKINGS: tuple[tuple[tuple[str, int], ...], ...] = (
    (("FST", 1),),
    (("FST", 1),),
)

# ---------- other bookings ----------

UPCOMING_EXTRA_BOOKINGS = 15  # on top of the 13 above: 28 upcoming confirmed
PAST_BOOKINGS = 8
CANCELLED_BOOKINGS = 4
CONFIRMED_YESTERDAY = 3  # so yesterday's export has confirmations
CANCELLED_YESTERDAY = 1  # and a cancellation
BB_SHARE_PERCENT = 40
MAX_UNITS_PER_BOOKING = DEFAULT_MAX_UNITS_PER_BOOKING  # A-25, same rule as the app

# ---------- promo codes ----------


@dataclass(frozen=True)
class PromoPlan:
    code: str
    percent_off: int
    valid_from_offset_days: int
    valid_to_offset_days: int
    max_uses: int | None
    seeded_uses: int  # bookings in the seed that use this code


PROMOS: tuple[PromoPlan, ...] = (
    PromoPlan("WELCOME10", 10, -30, 180, None, 4),  # valid
    PromoPlan("MONSOON15", 15, -150, -30, None, 0),  # expired
    PromoPlan("COFFEE20", 20, -30, 90, 5, 5),  # usage cap reached
)

# ---------- users ----------

# Every invented booking guest gets a guest account, because signing in is required to
# book (A-43). Those accounts cannot log in: their password hash is this marker, which
# no password matches. Only the four demo accounts below can log in (A-78).
UNUSABLE_PASSWORD_HASH = "!"


@dataclass(frozen=True)
class UserPlan:
    email: str
    full_name: str
    role: str
    team: str | None
    is_gm: bool
    phone: str | None
    # Demo login, documented in the README for reviewers. A real production deployment
    # would not load demo accounts.
    password: str


DEMO_GUEST_EMAIL = "guest@example.com"
USERS: tuple[UserPlan, ...] = (
    UserPlan(
        DEMO_GUEST_EMAIL, "Demo Guest", "guest", None, False, "+91 00000 00001", "Guest-Demo-2026"
    ),
    UserPlan(
        "reservations@example.com",
        "Reservations Desk",
        "staff",
        "reservations",
        False,
        None,
        "Reservations-Demo-2026",
    ),
    UserPlan(
        "events@example.com", "Events Team", "staff", "events", False, None, "Events-Demo-2026"
    ),
    UserPlan("gm@example.com", "General Manager", "staff", None, True, None, "GM-Demo-2026"),
)
DEMO_GUEST_BOOKINGS = ("past", "upcoming", "cancelled")

# ---------- invented guest names (all fake) ----------

GUEST_NAMES: tuple[str, ...] = (
    "Aarav Menon",
    "Diya Kulkarni",
    "Kabir Shetty",
    "Ananya Iyer",
    "Rohan Bhat",
    "Meera Nair",
    "Vikram Rao",
    "Isha Desai",
    "Arjun Hegde",
    "Nisha Pillai",
    "Siddharth Joshi",
    "Kavya Reddy",
    "Aditya Gowda",
    "Priya Varma",
    "Karthik Naidu",
    "Sneha Patil",
    "Rahul Kamath",
    "Tara Shenoy",
    "Nikhil Prabhu",
    "Pooja Acharya",
    "Varun Kini",
    "Lakshmi Murthy",
    "Dev Malhotra",
    "Riya Sen",
    "Manav Chawla",
    "Aisha Khan",
    "Farhan Qureshi",
    "Neha Bansal",
    "Sameer Ghosh",
    "Zoya Mirza",
    "Ishaan Kapoor",
    "Anjali Das",
    "Omkar Jain",
    "Sana Fernandes",
    "Tanvi Mehta",
    "Yash Agarwal",
    "Gauri Saxena",
    "Pranav Tiwari",
    "Maya Pinto",
    "Rehan Siddiqui",
)


def fake_email(full_name: str) -> str:
    return full_name.lower().replace(" ", ".") + "@example.com"


def fake_phone(n: int) -> str:
    # Indian mobile numbers never start with 0, so these are obviously fake.
    return f"+91 00000 {n:05d}"


# ---------- enquiries ----------

# Channel per enquiry, by position in sample_enquiries.json (A-35).
ENQUIRY_CHANNEL_CYCLE = ("web", "email", "whatsapp", "web", "phone")
ENQUIRY_SPREAD_HOURS = 72  # received over the last three days
CONSENT_VERSION = "v1"
