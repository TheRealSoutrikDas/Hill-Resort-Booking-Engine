"""Small builders for tests: each creates only the columns a table requires, flushes,
and returns the row. Shared by the integration tests from step 4 onwards."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import (
    Allotment,
    Booking,
    DailyRate,
    Hold,
    HoldItem,
    HoldItemNight,
    Payment,
    RatePlan,
    RoomType,
    User,
)
from app.services.holds import HoldLineRequest, HoldRequest, HoldRules
from app.services.pricing import GstRule

STAY = date(2027, 2, 12)
NOW = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


def room_type(
    db: Session, code: str = "DLX", total_units: int = 10, max_guests: int = 3
) -> RoomType:
    rt = RoomType(
        code=code, name=f"{code} room", kind="room", total_units=total_units, max_guests=max_guests
    )
    db.add(rt)
    db.flush()
    return rt


def rate_plan(db: Session, code: str = "RO", is_active: bool = True) -> RatePlan:
    rp = RatePlan(code=code, name=f"{code} plan", is_active=is_active)
    db.add(rp)
    db.flush()
    return rp


def daily_rate(db: Session, rt: RoomType, rp: RatePlan, night: date, price_paise: int) -> DailyRate:
    row = DailyRate(
        room_type_id=rt.id, rate_plan_id=rp.id, stay_date=night, price_paise=price_paise
    )
    db.add(row)
    db.flush()
    return row


def allotment(
    db: Session,
    rt: RoomType,
    night: date,
    total_for_web: int,
    sold: int = 0,
    is_blackout: bool = False,
) -> Allotment:
    row = Allotment(
        room_type_id=rt.id,
        stay_date=night,
        total_for_web=total_for_web,
        sold=sold,
        is_blackout=is_blackout,
    )
    db.add(row)
    db.flush()
    return row


def guest(db: Session, email: str | None = None) -> User:
    """A guest account. Every hold and booking needs one (A-43)."""
    u = User(
        email=email or f"guest-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Test Guest",
        role="guest",
    )
    db.add(u)
    db.flush()
    return u


def hold(db: Session, user: User | None = None, **overrides: object) -> Hold:
    values: dict[str, object] = dict(
        user_id=(user or guest(db)).id,
        check_in=STAY,
        check_out=STAY + timedelta(days=2),
        subtotal_paise=1_900_000,
        discount_paise=0,
        tax_paise=228_000,
        total_paise=2_128_000,
        expires_at=NOW + timedelta(minutes=10),
    )
    values.update(overrides)
    h = Hold(**values)
    db.add(h)
    db.flush()
    return h


def hold_for_stock(
    db: Session,
    lines: Sequence[tuple[RoomType, int]],
    nights: Sequence[date],
    *,
    expires_at: datetime,
    status: str = "active",
) -> Hold:
    """A hold that takes `units` of each room type on every night (prices are dummies)."""
    h = hold(
        db,
        check_in=nights[0],
        check_out=nights[-1] + timedelta(days=1),
        expires_at=expires_at,
        status=status,
    )
    rp = rate_plan(db, code=f"P{uuid.uuid4().hex[:6]}")
    for line_number, (rt, units) in enumerate(lines, start=1):
        item = HoldItem(
            hold_id=h.id,
            line_number=line_number,
            room_type_id=rt.id,
            rate_plan_id=rp.id,
            units=units,
            guests=units,
            subtotal_paise=1,
            tax_paise=0,
        )
        item.nights = [
            HoldItemNight(stay_date=n, rate_paise=1, tax_paise=0, tax_rate_bp=500) for n in nights
        ]
        db.add(item)
    db.flush()
    return h


def payment(db: Session, h: Hold, key: str | None = None, status: str = "succeeded") -> Payment:
    p = Payment(
        hold_id=h.id,
        idempotency_key=key or uuid.uuid4().hex,
        amount_paise=h.total_paise,
        status=status,
    )
    db.add(p)
    db.flush()
    return p


def booking(db: Session, h: Hold, p: Payment, **overrides: object) -> Booking:
    values: dict[str, object] = dict(
        reference="BK-7F3K9QXM",
        user_id=h.user_id,
        hold_id=h.id,
        payment_id=p.id,
        check_in=h.check_in,
        check_out=h.check_out,
        guest_name="Asha Rao",
        guest_email="asha@example.com",
        guest_phone="+91 00000 00001",
        subtotal_paise=h.subtotal_paise,
        discount_paise=h.discount_paise,
        tax_paise=h.tax_paise,
        total_paise=h.total_paise,
        confirmed_at=NOW,
    )
    values.update(overrides)
    b = Booking(**values)
    db.add(b)
    db.flush()
    return b


def staff(db: Session, email: str, **overrides: object) -> User:
    values: dict[str, object] = dict(
        email=email, password_hash="x", full_name="Staff", role="staff"
    )
    values.update(overrides)
    u = User(**values)
    db.add(u)
    db.flush()
    return u


# ---------- a small bookable catalogue (steps 5 onwards) ----------

N2 = STAY + timedelta(days=1)
NIGHTS = [STAY, N2]
RULES = HoldRules(
    tz=ZoneInfo("Asia/Kolkata"),
    horizon_days=180,
    max_nights=14,
    max_units=4,
    ttl_minutes=10,
    lock_timeout_ms=5_000,
    gst_rule=GstRule(threshold_paise=750_000, low_rate_bp=500, high_rate_bp=1_800),
)
DLX_RO = 600_000  # Rs 6,000: 5% GST
FST_RO = 1_000_000  # Rs 10,000: 18% GST


@dataclass
class Catalogue:
    dlx: RoomType
    fst: RoomType
    ro: RatePlan
    bb: RatePlan
    off: RatePlan  # inactive
    user: User


def catalogue(db: Session, dlx_web: int = 4, fst_web: int = 3) -> Catalogue:
    dlx = room_type(db, "DLX", max_guests=3)
    fst = room_type(db, "FST", max_guests=4)
    ro, bb, off = rate_plan(db, "RO"), rate_plan(db, "BB"), rate_plan(db, "OFF", is_active=False)
    for night in NIGHTS:
        allotment(db, dlx, night, dlx_web)
        allotment(db, fst, night, fst_web)
        for rt, base in ((dlx, DLX_RO), (fst, FST_RO)):
            daily_rate(db, rt, ro, night, base)
            daily_rate(db, rt, bb, night, base + 120_000)
            daily_rate(db, rt, off, night, base)
    return Catalogue(dlx, fst, ro, bb, off, guest(db))


def line(rt: RoomType, rp: RatePlan, units: int = 1, guests: int | None = None) -> HoldLineRequest:
    return HoldLineRequest(rt.id, rp.id, units, units * 2 if guests is None else guests)


def request(*lines: HoldLineRequest, nights: int = 2) -> HoldRequest:
    return HoldRequest(STAY, STAY + timedelta(days=nights), lines)
