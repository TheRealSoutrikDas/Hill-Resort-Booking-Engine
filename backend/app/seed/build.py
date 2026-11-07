"""Writes the seed rows inside the caller's transaction (the command line commits).

Order: users, catalogue, rates, then the bookings are planned in memory so the
allotments can be written with the right `sold` counts, then bookings, enquiries,
and finally a self-check that refuses inconsistent data.
"""

import random
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Allotment,
    Booking,
    BookingItem,
    DailyRate,
    Enquiry,
    Hold,
    HoldItem,
    HoldItemNight,
    Payment,
    PromoCode,
    RatePlan,
    RoomType,
    User,
)
from app.db.models.enums import BookingStatus, HoldStatus, PaymentStatus
from app.enquiry_samples import SampleEnquiryFile
from app.seed import plan
from app.services.passwords import hash_password
from app.services.pricing import GstRule, LineInput, price_stay
from app.services.references import generate_booking_reference

PAISE_PER_RUPEE = 100


class SeedError(RuntimeError):
    """The seed would produce inconsistent data, or cannot run safely."""


@dataclass(frozen=True)
class SeedContext:
    today: date  # business date in the business timezone
    now: datetime  # timezone-aware
    tz: ZoneInfo
    gst_rule: GstRule

    def at(self, day: date, hour: int, minute: int = 0) -> datetime:
        """A local business time on `day`, as an aware UTC datetime."""
        return datetime.combine(day, time(hour, minute), tzinfo=self.tz).astimezone(UTC)

    @property
    def first_rate_night(self) -> date:
        return self.today - timedelta(days=plan.RATES_DAYS_BEFORE_TODAY)

    @property
    def last_rate_night(self) -> date:
        return self.today + timedelta(days=plan.RATES_DAYS_AFTER_TODAY - 1)

    def rate_nights(self) -> list[date]:
        count = (self.last_rate_night - self.first_rate_night).days + 1
        return [self.first_rate_night + timedelta(days=i) for i in range(count)]


@dataclass
class BookingSpec:
    lines: tuple[tuple[str, int], ...]  # (room type code, units)
    check_in: date
    nights: int
    status: str
    confirmed_at: datetime
    kind: str  # past, upcoming or cancelled
    cancelled_at: datetime | None = None
    rate_plan: str = "RO"
    promo: str | None = None
    demo_guest: bool = False

    @property
    def check_out(self) -> date:
        return self.check_in + timedelta(days=self.nights)

    def stay_nights(self) -> list[date]:
        return [self.check_in + timedelta(days=i) for i in range(self.nights)]


@dataclass(frozen=True)
class SeedSummary:
    demo_accounts: int
    booking_guest_accounts: int
    room_units: int
    villa_units: int
    rate_rows: int
    allotment_rows: int
    bookings_confirmed: int
    bookings_cancelled: int
    enquiries: int
    one_left_friday: date
    sold_out_friday: date
    blackout_start: date


# ---------- safety ----------


def database_has_data(session: Session) -> bool:
    for model in (User, RoomType, Booking, Enquiry):
        if session.scalar(select(model).limit(1)) is not None:
            return True
    return False


def reset_database(session: Session) -> None:
    """Empty every application table and restart ids, inside the current transaction."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    # Forget objects loaded before the truncate; their rows no longer exist.
    session.expunge_all()


# ---------- booking plan (in memory) ----------


def _recent_confirmation(rng: random.Random, ctx: SeedContext) -> datetime:
    day = ctx.today - timedelta(days=rng.randint(2, 28))
    return ctx.at(day, rng.randint(8, 21), rng.randint(0, 59))


class _Capacity:
    """Tracks web units sold per room type per night while planning bookings."""

    def __init__(self, ctx: SeedContext) -> None:
        self.ctx = ctx
        self.web = {rt.code: plan.web_allotment(rt.units) for rt in plan.ROOM_TYPES}
        self.used: Counter[tuple[str, date]] = Counter()
        self.blackout = set(plan.blackout_nights(ctx.today))
        one_left = plan.one_left_friday(ctx.today)
        # Extra bookings must not touch the "one unit left" nights.
        self.reserved = {(plan.ONE_LEFT_ROOM_TYPE, one_left + timedelta(days=i)) for i in (0, 1)}

    def fits(self, spec: BookingSpec, check_reserved: bool = True) -> bool:
        for night in spec.stay_nights():
            if not self.ctx.first_rate_night <= night <= self.ctx.last_rate_night:
                return False
            if night in self.blackout:
                return False
            for code, units in spec.lines:
                if check_reserved and (code, night) in self.reserved:
                    return False
                if self.used[(code, night)] + units > self.web[code]:
                    return False
        return True

    def take(self, spec: BookingSpec) -> None:
        for night in spec.stay_nights():
            for code, units in spec.lines:
                self.used[(code, night)] += units


def _random_lines(rng: random.Random, mixed: bool) -> tuple[tuple[str, int], ...]:
    codes = [rt.code for rt in plan.ROOM_TYPES]
    weights = [rt.units for rt in plan.ROOM_TYPES]
    if mixed:
        first, second = rng.sample(codes, 2)
        return ((first, 1), (second, 1))
    code = rng.choices(codes, weights=weights)[0]
    return ((code, 2 if rng.random() < 0.25 else 1),)


def plan_bookings(rng: random.Random, ctx: SeedContext) -> list[BookingSpec]:
    capacity = _Capacity(ctx)
    upcoming: list[BookingSpec] = []

    # Deliberate states first, so nothing else can take their stock.
    for friday, groups in (
        (plan.sold_out_friday(ctx.today), plan.SOLD_OUT_BOOKINGS),
        (plan.one_left_friday(ctx.today), plan.ONE_LEFT_BOOKINGS),
    ):
        for lines in groups:
            spec = BookingSpec(
                lines,
                friday,
                2,
                BookingStatus.CONFIRMED,
                _recent_confirmation(rng, ctx),
                "upcoming",
            )
            if not capacity.fits(spec, check_reserved=False):
                raise SeedError(f"deliberate booking does not fit: {lines} on {friday}")
            capacity.take(spec)
            upcoming.append(spec)

    extras: list[BookingSpec] = []
    while len(extras) < plan.UPCOMING_EXTRA_BOOKINGS:
        spec = BookingSpec(
            _random_lines(rng, mixed=not extras),  # the first extra mixes two room types
            ctx.today + timedelta(days=rng.randint(1, 120)),
            rng.choice((1, 2, 2, 3, 4)),
            BookingStatus.CONFIRMED,
            _recent_confirmation(rng, ctx),
            "upcoming",
        )
        if capacity.fits(spec):
            capacity.take(spec)
            extras.append(spec)
    yesterday = ctx.today - timedelta(days=1)
    for spec, hour in zip(extras[: plan.CONFIRMED_YESTERDAY], (10, 13, 17), strict=True):
        spec.confirmed_at = ctx.at(yesterday, hour, 15)
    upcoming.extend(extras)

    past: list[BookingSpec] = []
    while len(past) < plan.PAST_BOOKINGS:
        nights = rng.randint(1, 3)
        check_in = ctx.today - timedelta(days=rng.randint(nights + 1, 55))
        confirmed_day = check_in - timedelta(days=rng.randint(7, 40))
        spec = BookingSpec(
            _random_lines(rng, mixed=False),
            check_in,
            nights,
            BookingStatus.CONFIRMED,
            ctx.at(confirmed_day, rng.randint(8, 21), rng.randint(0, 59)),
            "past",
        )
        if capacity.fits(spec):
            capacity.take(spec)
            past.append(spec)

    cancelled: list[BookingSpec] = []
    while len(cancelled) < plan.CANCELLED_BOOKINGS:
        spec = BookingSpec(
            _random_lines(rng, mixed=False),
            ctx.today + timedelta(days=rng.randint(10, 90)),
            rng.randint(1, 3),
            BookingStatus.CANCELLED,
            ctx.at(ctx.today - timedelta(days=rng.randint(5, 25)), rng.randint(8, 21)),
            "cancelled",
        )
        # Cancelled bookings hold no stock, but still avoid closed nights.
        if capacity.fits(spec):
            first_possible = spec.confirmed_at.astimezone(ctx.tz).date() + timedelta(days=1)
            if len(cancelled) < plan.CANCELLED_YESTERDAY:
                day = yesterday
            else:
                day = first_possible + timedelta(
                    days=rng.randint(0, (yesterday - first_possible).days)
                )
            spec.cancelled_at = ctx.at(day, 15, rng.randint(0, 59))
            cancelled.append(spec)

    for spec in upcoming + past + cancelled:
        spec.rate_plan = "BB" if rng.random() < plan.BB_SHARE_PERCENT / 100 else "RO"

    # Promo codes go to recent bookings, confirmed while the code was valid.
    promo_candidates = upcoming + cancelled
    uses = [p.code for p in plan.PROMOS for _ in range(p.seeded_uses)]
    for spec, code in zip(rng.sample(promo_candidates, len(uses)), uses, strict=True):
        spec.promo = code

    past[0].demo_guest = True
    extras[-1].demo_guest = True
    cancelled[-1].demo_guest = True

    return sorted(upcoming + past + cancelled, key=lambda s: s.confirmed_at)


# ---------- writers ----------


def _seed_users(session: Session) -> dict[str, User]:
    users = {
        u.email: User(
            email=u.email,
            password_hash=hash_password(u.password),
            full_name=u.full_name,
            role=u.role,
            team=u.team,
            is_gm=u.is_gm,
            phone=u.phone,
        )
        for u in plan.USERS
    }
    session.add_all(users.values())
    return users


def _seed_catalogue(session: Session) -> tuple[dict[str, RoomType], dict[str, RatePlan]]:
    room_types = {
        rt.code: RoomType(
            code=rt.code,
            name=rt.name,
            kind=rt.kind,
            total_units=rt.units,
            max_guests=rt.max_guests,
            description=rt.description,
            sort_order=i,
        )
        for i, rt in enumerate(plan.ROOM_TYPES)
    }
    rate_plans = {
        code: RatePlan(code=code, name=name, description=description)
        for code, name, description in plan.RATE_PLANS
    }
    session.add_all([*room_types.values(), *rate_plans.values()])
    session.flush()
    return room_types, rate_plans


def _rates_paise(ctx: SeedContext) -> dict[tuple[str, str, date], int]:
    return {
        (rt.code, code, night): plan.rate_rupees(rt, code, night) * PAISE_PER_RUPEE
        for rt in plan.ROOM_TYPES
        for code, _name, _description in plan.RATE_PLANS
        for night in ctx.rate_nights()
    }


def _seed_promos(
    session: Session, ctx: SeedContext, specs: list[BookingSpec]
) -> dict[str, PromoCode]:
    used = Counter(s.promo for s in specs if s.promo)
    promos = {
        p.code: PromoCode(
            code=p.code,
            percent_off=p.percent_off,
            valid_from=ctx.today + timedelta(days=p.valid_from_offset_days),
            valid_to=ctx.today + timedelta(days=p.valid_to_offset_days),
            max_uses=p.max_uses,
            used_count=used[p.code],  # A-20: cancelled bookings keep their use
        )
        for p in plan.PROMOS
    }
    session.add_all(promos.values())
    session.flush()
    return promos


def _line_guests(rng: random.Random, code: str, units: int) -> int:
    max_guests = next(rt.max_guests for rt in plan.ROOM_TYPES if rt.code == code)
    guests = units * rng.randint(1, 2)
    if max_guests >= 4 and rng.random() < 0.3:
        guests += 1  # a child
    return min(guests, units * max_guests)


def _seed_bookings(
    session: Session,
    rng: random.Random,
    ctx: SeedContext,
    specs: list[BookingSpec],
    rates: dict[tuple[str, str, date], int],
    users: dict[str, User],
    room_types: dict[str, RoomType],
    rate_plans: dict[str, RatePlan],
    promos: dict[str, PromoCode],
) -> int:
    """Write every planned booking. Returns how many booking-guest accounts it created."""
    demo = users[plan.DEMO_GUEST_EMAIL]
    references: set[str] = set()
    booking_guests = 0
    for n, spec in enumerate(specs):
        if spec.demo_guest:
            account = demo
        else:
            # Signing in is required to book (A-43), so every invented guest has an
            # account. Like all seeded accounts it cannot log in (A-34).
            name = plan.GUEST_NAMES[n % len(plan.GUEST_NAMES)]
            account = User(
                email=plan.fake_email(name),
                password_hash=plan.UNUSABLE_PASSWORD_HASH,
                full_name=name,
                role="guest",
                phone=plan.fake_phone(100 + n),
            )
            session.add(account)
            session.flush()
            booking_guests += 1
        user_id, name, email, phone = account.id, account.full_name, account.email, account.phone

        promo = promos[spec.promo] if spec.promo else None
        price = price_stay(
            [
                LineInput(
                    {night: rates[(code, spec.rate_plan, night)] for night in spec.stay_nights()},
                    units,
                )
                for code, units in spec.lines
            ],
            promo.percent_off if promo else 0,
            ctx.gst_rule,
        )

        hold_created = spec.confirmed_at - timedelta(minutes=6)
        hold = Hold(
            id=uuid.UUID(int=rng.getrandbits(128), version=4),
            check_in=spec.check_in,
            check_out=spec.check_out,
            user_id=user_id,
            guest_name=name,
            guest_email=email,
            guest_phone=phone,
            promo_code_id=promo.id if promo else None,
            subtotal_paise=price.subtotal_paise,
            discount_paise=price.discount_paise,
            tax_paise=price.tax_paise,
            total_paise=price.total_paise,
            status=HoldStatus.CONVERTED,
            expires_at=hold_created + timedelta(minutes=10),
            created_at=hold_created,
        )
        for line_number, ((code, units), line) in enumerate(
            zip(spec.lines, price.lines, strict=True), start=1
        ):
            hold.items.append(
                HoldItem(
                    line_number=line_number,
                    room_type_id=room_types[code].id,
                    rate_plan_id=rate_plans[spec.rate_plan].id,
                    units=units,
                    guests=_line_guests(rng, code, units),
                    subtotal_paise=line.subtotal_paise,
                    discount_paise=line.discount_paise,
                    tax_paise=line.tax_paise,
                    nights=[
                        HoldItemNight(
                            stay_date=night.stay_date,
                            rate_paise=night.rate_paise,
                            discount_paise=night.discount_paise,
                            tax_paise=night.tax_paise,
                            tax_rate_bp=night.tax_rate_bp,
                        )
                        for night in line.nights
                    ],
                )
            )
        cancelled = spec.status == BookingStatus.CANCELLED
        payment = Payment(
            hold_id=hold.id,
            idempotency_key=f"seed-{rng.getrandbits(64):016x}",
            provider="mock",
            provider_reference=f"MOCK-{rng.getrandbits(48):012X}",
            amount_paise=price.total_paise,
            # A-33: a cancelled booking is fully refunded.
            status=PaymentStatus.REFUNDED if cancelled else PaymentStatus.SUCCEEDED,
            created_at=spec.confirmed_at - timedelta(minutes=1),
            updated_at=spec.cancelled_at or spec.confirmed_at,
        )
        session.add(hold)
        session.add(payment)
        session.flush()

        reference = generate_booking_reference(rng)
        while reference in references:
            reference = generate_booking_reference(rng)
        references.add(reference)

        session.add(
            Booking(
                reference=reference,
                hold_id=hold.id,
                payment_id=payment.id,
                user_id=user_id,
                check_in=spec.check_in,
                check_out=spec.check_out,
                guest_name=name,
                guest_email=email,
                guest_phone=phone,
                promo_code_id=hold.promo_code_id,
                subtotal_paise=price.subtotal_paise,
                discount_paise=price.discount_paise,
                tax_paise=price.tax_paise,
                total_paise=price.total_paise,
                status=spec.status,
                confirmed_at=spec.confirmed_at,
                cancelled_at=spec.cancelled_at,
                created_at=spec.confirmed_at,
                items=[
                    BookingItem(
                        line_number=item.line_number,
                        hold_item_id=item.id,
                        room_type_id=item.room_type_id,
                        rate_plan_id=item.rate_plan_id,
                        units=item.units,
                        guests=item.guests,
                        subtotal_paise=item.subtotal_paise,
                        discount_paise=item.discount_paise,
                        tax_paise=item.tax_paise,
                    )
                    for item in hold.items
                ],
            )
        )
    session.flush()
    return booking_guests


def _seed_enquiries(
    session: Session, rng: random.Random, ctx: SeedContext, samples: SampleEnquiryFile
) -> int:
    count = len(samples.enquiries)
    span_minutes = plan.ENQUIRY_SPREAD_HOURS * 60
    for i, sample in enumerate(samples.enquiries):
        channel = plan.ENQUIRY_CHANNEL_CYCLE[i % len(plan.ENQUIRY_CHANNEL_CYCLE)]
        minutes_ago = (count - 1 - i) * span_minutes // max(count - 1, 1) + rng.randint(1, 20)
        received_at = ctx.now - timedelta(minutes=minutes_ago)
        name = plan.GUEST_NAMES[(i * 7 + 3) % len(plan.GUEST_NAMES)]
        uses_email = channel in ("web", "email")
        session.add(
            Enquiry(
                reference=sample.id,
                channel=channel,
                message=sample.message,
                contact_name=name,
                contact_email=plan.fake_email(name) if uses_email else None,
                contact_phone=None if uses_email else plan.fake_phone(500 + i),
                consent_at=received_at if channel == "web" else None,
                consent_version=plan.CONSENT_VERSION if channel == "web" else None,
                received_at=received_at,
                # Classified by the pipeline in step 23; until then every enquiry is pending.
                status="pending",
                created_at=received_at,
                updated_at=received_at,
            )
        )
    session.flush()
    return count


# ---------- self-check ----------


def verify(session: Session) -> None:
    """Refuse to commit data that breaks the rules the services rely on."""
    expected_sold: Counter[tuple[int, date]] = Counter()
    bookings = session.scalars(select(Booking).where(Booking.status == BookingStatus.CONFIRMED))
    for booking in bookings:
        for item in booking.items:
            for i in range((booking.check_out - booking.check_in).days):
                expected_sold[(item.room_type_id, booking.check_in + timedelta(days=i))] += (
                    item.units
                )
    problems = []
    for allotment in session.scalars(select(Allotment)):
        key = (allotment.room_type_id, allotment.stay_date)
        if allotment.sold != expected_sold.pop(key, 0):
            problems.append(f"sold mismatch for room type {key[0]} on {key[1]}")
    problems += [f"booking on a night with no allotment row: {key}" for key in expected_sold]

    for promo in session.scalars(select(PromoCode)):
        uses = session.scalar(
            select(func.count()).select_from(Booking).where(Booking.promo_code_id == promo.id)
        )
        if promo.used_count != uses:
            problems.append(f"promo {promo.code}: used_count {promo.used_count} != {uses} bookings")
    if problems:
        raise SeedError("seed self-check failed:\n  " + "\n  ".join(problems))


# ---------- entry point ----------


def seed(session: Session, ctx: SeedContext, samples: SampleEnquiryFile) -> SeedSummary:
    rng = random.Random(plan.RANDOM_SEED)

    users = _seed_users(session)
    room_types, rate_plans = _seed_catalogue(session)

    rates = _rates_paise(ctx)
    session.execute(
        insert(DailyRate),
        [
            {
                "room_type_id": room_types[code].id,
                "rate_plan_id": rate_plans[plan_code].id,
                "stay_date": night,
                "price_paise": price,
            }
            for (code, plan_code, night), price in rates.items()
        ],
    )

    specs = plan_bookings(rng, ctx)
    sold: Counter[tuple[str, date]] = Counter()
    for spec in specs:
        if spec.status == BookingStatus.CONFIRMED:
            for night in spec.stay_nights():
                for code, units in spec.lines:
                    sold[(code, night)] += units
    blackout = set(plan.blackout_nights(ctx.today))
    session.execute(
        insert(Allotment),
        [
            {
                "room_type_id": room_types[rt.code].id,
                "stay_date": night,
                "total_for_web": plan.web_allotment(rt.units),
                "sold": sold[(rt.code, night)],
                "is_blackout": night in blackout,
            }
            for rt in plan.ROOM_TYPES
            for night in ctx.rate_nights()
        ],
    )

    promos = _seed_promos(session, ctx, specs)
    session.flush()
    booking_guest_accounts = _seed_bookings(
        session, rng, ctx, specs, rates, users, room_types, rate_plans, promos
    )
    enquiry_count = _seed_enquiries(session, rng, ctx, samples)
    verify(session)

    return SeedSummary(
        demo_accounts=len(users),
        booking_guest_accounts=booking_guest_accounts,
        room_units=sum(rt.units for rt in plan.ROOM_TYPES if rt.kind == "room"),
        villa_units=sum(rt.units for rt in plan.ROOM_TYPES if rt.kind == "villa"),
        rate_rows=len(rates),
        allotment_rows=len(plan.ROOM_TYPES) * len(ctx.rate_nights()),
        bookings_confirmed=sum(1 for s in specs if s.status == BookingStatus.CONFIRMED),
        bookings_cancelled=sum(1 for s in specs if s.status == BookingStatus.CANCELLED),
        enquiries=enquiry_count,
        one_left_friday=plan.one_left_friday(ctx.today),
        sold_out_friday=plan.sold_out_friday(ctx.today),
        blackout_start=plan.blackout_nights(ctx.today)[0],
    )
