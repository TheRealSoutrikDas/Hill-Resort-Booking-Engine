"""Zero website overbookings, under real parallel load (D-29).

Every simulated guest runs in its own thread on its own database connection, and all
start at the same instant. Each scenario runs ROUNDS times, because one passing race
proves little. After every scenario the stock invariants are checked.
"""

import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Booking, Hold, Payment, PromoCode
from app.services.bookings import (
    HOLD_ALREADY_PAID,
    HOLD_EXPIRED_SOLD_OUT,
    PAYMENT_ALREADY_REFUNDED,
    cancel_booking,
    confirm_booking,
)
from app.services.errors import InvalidPromoCode, NotAvailable
from app.services.holds import HoldLineRequest, HoldRequest, create_hold, set_guest_details
from tests.factories import (
    NOW,
    RULES,
    STAY,
    allotment,
    catalogue,
    daily_rate,
    guest,
    line,
    promo,
    rate_plan,
    request,
    room_type,
)
from tests.parallel import Outcome, assert_stock_consistent, run_in_parallel

ROUNDS = int(os.environ.get("CONCURRENCY_ROUNDS", "5"))
GUESTS = 10
LATER = NOW + timedelta(minutes=11)  # a hold made at NOW has expired

pytestmark = pytest.mark.parametrize("round_", range(ROUNDS), ids=lambda r: f"round{r}")


# ---------- small steps, each its own transaction like a separate request ----------


def hold_step(s: Session, user_id: int, req: HoldRequest, now=NOW):
    with s.begin():
        return create_hold(s, user_id, req, now=now, rules=RULES)


def details_step(s: Session, user_id: int, hold_id, now=NOW) -> None:
    with s.begin():
        set_guest_details(
            s,
            user_id,
            hold_id,
            name="Asha Rao",
            email="asha@example.com",
            phone="+91 00000 00042",
            now=now,
        )


def payment_step(s: Session, hold_id) -> int:
    """What step 10's provider will do: record a payment it has just captured."""
    with s.begin():
        hold = s.get(Hold, hold_id)
        p = Payment(
            hold_id=hold_id, idempotency_key=uuid.uuid4().hex, amount_paise=hold.total_paise
        )
        s.add(p)
        s.flush()
        return p.id


def confirm_step(s: Session, user_id: int, hold_id, payment_id: int, now=NOW):
    with s.begin():
        outcome = confirm_booking(s, user_id, hold_id, payment_id, now=now, rules=RULES)
        return (outcome.booking.id if outcome.booking else None, outcome.failure)


def ready_to_pay(factory: sessionmaker[Session], user_id: int, req: HoldRequest, now=NOW):
    with factory() as s:
        result = hold_step(s, user_id, req, now)
        details_step(s, user_id, result.hold_id, now)
        return result.hold_id, payment_step(s, result.hold_id)


def errors(outcomes: list[Outcome]) -> list[BaseException]:
    return [o.error for o in outcomes if o.error is not None]


def only_sold_out_errors(outcomes: list[Outcome]) -> None:
    unexpected = [e for e in errors(outcomes) if not isinstance(e, NotAvailable)]
    assert not unexpected, f"unexpected errors: {unexpected!r}"


def check_stock(factory: sessionmaker[Session], now=NOW) -> None:
    with factory() as s:
        assert_stock_consistent(s, now)


def count(factory: sessionmaker[Session], model, *where) -> int:
    with factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


# ---------- 1. ten guests, one last unit ----------


def test_ten_guests_one_last_unit_exactly_one_hold(committed, round_) -> None:
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=1)
        users = [guest(s).id for _ in range(GUESTS)]
        req = request(line(c.dlx, c.ro))

    outcomes = run_in_parallel(committed, [lambda s, u=u: hold_step(s, u, req) for u in users])

    only_sold_out_errors(outcomes)
    assert sum(o.error is None for o in outcomes) == 1
    assert count(committed, Hold, Hold.status == "active") == 1
    check_stock(committed)


def test_ten_guests_one_last_unit_full_flow_exactly_one_booking(committed, round_) -> None:
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=1)
        users = [guest(s).id for _ in range(GUESTS)]
        req = request(line(c.dlx, c.ro))

    def book(s: Session, user_id: int):
        try:
            hold_id = hold_step(s, user_id, req).hold_id
        except NotAvailable:
            return "sold out"
        details_step(s, user_id, hold_id)
        return confirm_step(s, user_id, hold_id, payment_step(s, hold_id))

    outcomes = run_in_parallel(committed, [lambda s, u=u: book(s, u) for u in users])

    assert not errors(outcomes)
    results = [o.value for o in outcomes]
    assert results.count("sold out") == GUESTS - 1
    confirmed = [r for r in results if r != "sold out"]
    assert len(confirmed) == 1 and confirmed[0][0] is not None
    assert count(committed, Booking) == 1
    check_stock(committed)


# ---------- 2. multi-night stay where only one night is full ----------


def three_night_stock(s: Session, per_night: tuple[int, int, int]):
    rt, rp = room_type(s, "DLX"), rate_plan(s, "RO")
    nights = [STAY + timedelta(days=i) for i in range(3)]
    for night, web in zip(nights, per_night, strict=True):
        allotment(s, rt, night, web)
        daily_rate(s, rt, rp, night, 600_000)
    return rt, rp, nights


def stay(rt, rp, check_in: date, nights: int) -> HoldRequest:
    return HoldRequest(
        check_in, check_in + timedelta(days=nights), [HoldLineRequest(rt.id, rp.id, 1, 2)]
    )


def test_three_night_stay_with_one_tight_night(committed, round_) -> None:
    with committed() as s, s.begin():
        rt, rp, nights = three_night_stock(s, (5, 1, 5))
        users = [guest(s).id for _ in range(GUESTS)]
    req = stay(rt, rp, nights[0], 3)

    outcomes = run_in_parallel(committed, [lambda s, u=u: hold_step(s, u, req) for u in users])

    only_sold_out_errors(outcomes)
    assert sum(o.error is None for o in outcomes) == 1
    for error in errors(outcomes):  # every loser was short on the middle night only
        assert [sf.stay_date for sf in error.shortfalls] == [nights[1]]
    check_stock(committed)


def test_guests_avoiding_the_tight_night_all_succeed(committed, round_) -> None:
    with committed() as s, s.begin():
        rt, rp, nights = three_night_stock(s, (10, 1, 10))
        users = [guest(s).id for _ in range(GUESTS)]
    needs_tight = [stay(rt, rp, nights[0], 3)] * 5  # includes the middle night
    avoids_tight = [stay(rt, rp, nights[0], 1)] * 3 + [stay(rt, rp, nights[2], 1)] * 2
    requests = needs_tight + avoids_tight

    outcomes = run_in_parallel(
        committed,
        [lambda s, u=u, r=r: hold_step(s, u, r) for u, r in zip(users, requests, strict=True)],
    )

    only_sold_out_errors(outcomes)
    assert sum(o.error is None for o in outcomes[:5]) == 1  # exactly one gets the middle night
    assert all(o.error is None for o in outcomes[5:])  # nobody else is blocked
    check_stock(committed)


# ---------- 3. expired holds ----------


def test_expired_hold_owner_and_new_guests_race_for_the_unit(committed, round_) -> None:
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=1)
        owner = c.user.id
        others = [guest(s).id for _ in range(GUESTS - 1)]
        req = request(line(c.dlx, c.ro))
    hold_id, payment_id = ready_to_pay(committed, owner, req)  # held at NOW, paid late

    tasks = [lambda s: confirm_step(s, owner, hold_id, payment_id, now=LATER)]
    tasks += [lambda s, u=u: hold_step(s, u, req, now=LATER) for u in others]
    outcomes = run_in_parallel(committed, tasks)

    only_sold_out_errors(outcomes)
    booking_id, failure = outcomes[0].value
    new_holds = sum(o.error is None for o in outcomes[1:])
    if booking_id is not None:  # the owner won: nobody else got the unit
        assert new_holds == 0
    else:  # a new guest won: the owner's payment is refunded
        assert failure == HOLD_EXPIRED_SOLD_OUT and new_holds == 1
        with committed() as s:
            assert s.get(Payment, payment_id).status == "refund_pending"
    check_stock(committed, LATER)


# ---------- 4. double-submitted payments ----------
#
# Protected three ways: the allotment row lock and the hold row lock each serialize
# confirmations of one hold, and the unique bookings.hold_id and one-succeeded-payment
# index refuse a second booking even if both locks were missing (D-29).


def test_same_payment_submitted_ten_times_makes_one_booking(committed, round_) -> None:
    with committed() as s, s.begin():
        c = catalogue(s)
        owner = c.user.id
        req = request(line(c.dlx, c.ro))
    hold_id, payment_id = ready_to_pay(committed, owner, req)

    outcomes = run_in_parallel(
        committed, [lambda s: confirm_step(s, owner, hold_id, payment_id) for _ in range(GUESTS)]
    )

    assert not errors(outcomes)
    booking_ids = {o.value[0] for o in outcomes}
    assert len(booking_ids) == 1 and None not in booking_ids
    assert count(committed, Booking) == 1
    check_stock(committed)


def test_two_tabs_paying_for_one_hold_make_one_booking(committed, round_) -> None:
    with committed() as s, s.begin():
        c = catalogue(s)
        owner = c.user.id
        req = request(line(c.dlx, c.ro))
    hold_id, first = ready_to_pay(committed, owner, req)
    with committed() as s:
        second = payment_step(s, hold_id)
    payments = [first, second] * (GUESTS // 2)

    outcomes = run_in_parallel(
        committed, [lambda s, p=p: confirm_step(s, owner, hold_id, p) for p in payments]
    )

    assert not errors(outcomes)
    assert count(committed, Booking) == 1
    with committed() as s:
        statuses = sorted(s.get(Payment, p).status for p in (first, second))
    assert statuses == ["refund_pending", "succeeded"]
    failures = {o.value[1] for o in outcomes if o.value[0] is None}
    assert failures <= {HOLD_ALREADY_PAID, PAYMENT_ALREADY_REFUNDED}
    check_stock(committed)


# ---------- 5. no deadlocks between mixed-room bookings ----------


def test_opposite_line_orders_do_not_deadlock(committed, round_) -> None:
    """No deadlocks when bookings list their room types in opposite orders.

    Honest limit: Postgres usually scans these rows in one consistent order anyway, so
    this test also passes without the ORDER BY in the lock query. The ORDER BY makes the
    lock order a guarantee instead of an accident of the query plan (D-21, D-29)."""
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=GUESTS, fst_web=GUESTS)
        users = [guest(s).id for _ in range(GUESTS)]
        forward = request(line(c.dlx, c.ro), line(c.fst, c.ro))
        backward = request(line(c.fst, c.ro), line(c.dlx, c.ro))

    outcomes = run_in_parallel(
        committed,
        [
            lambda s, u=u, r=(forward if i % 2 else backward): hold_step(s, u, r)
            for i, u in enumerate(users)
        ],
    )

    assert not errors(outcomes), errors(outcomes)  # a deadlock would surface as an error
    assert count(committed, Hold) == GUESTS
    check_stock(committed)


# ---------- 6. cancel versus book ----------


def test_cancelling_the_last_unit_while_others_book(committed, round_) -> None:
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=1)
        owner = c.user.id
        others = [guest(s).id for _ in range(GUESTS - 1)]
        req = request(line(c.dlx, c.ro))
    hold_id, payment_id = ready_to_pay(committed, owner, req)
    with committed() as s:
        confirm_step(s, owner, hold_id, payment_id)
        reference = s.scalar(select(Booking.reference))

    def cancel(s: Session):
        with s.begin():
            cancel_booking(s, owner, reference, now=NOW, rules=RULES)

    tasks = [cancel] + [lambda s, u=u: hold_step(s, u, req) for u in others]
    outcomes = run_in_parallel(committed, tasks)

    only_sold_out_errors(outcomes)
    assert outcomes[0].error is None
    assert sum(o.error is None for o in outcomes[1:]) <= 1  # at most one takes the freed unit
    assert count(committed, Booking, Booking.status == "confirmed") == 0
    check_stock(committed)


# ---------- 7. ten guests, one last promo use ----------


def test_ten_guests_one_last_promo_use(committed, round_) -> None:
    """Each guest books a different night, so no allotment row is shared: the promo row
    lock alone must stop two guests taking the last use."""
    with committed() as s, s.begin():
        rt, rp = room_type(s, "DLX"), rate_plan(s, "RO")
        nights = [STAY + timedelta(days=i) for i in range(GUESTS)]
        for night in nights:
            allotment(s, rt, night, 1)
            daily_rate(s, rt, rp, night, 600_000)
        promo(s, "COFFEE20", 20, max_uses=5, used_count=4)
        users = [guest(s).id for _ in range(GUESTS)]

    def hold_with_code(s: Session, user_id: int, night: date):
        with s.begin():
            return create_hold(
                s, user_id, stay(rt, rp, night, 1), now=NOW, rules=RULES, promo_code="COFFEE20"
            )

    outcomes = run_in_parallel(
        committed,
        [lambda s, u=u, n=n: hold_with_code(s, u, n) for u, n in zip(users, nights, strict=True)],
    )

    unexpected = [e for e in errors(outcomes) if not isinstance(e, InvalidPromoCode)]
    assert not unexpected, unexpected
    assert {e.code for e in errors(outcomes)} <= {"promo_used_up"}
    assert sum(o.error is None for o in outcomes) == 1
    with committed() as s:
        code = s.scalar(select(PromoCode).where(PromoCode.code == "COFFEE20"))
        reserved = s.scalar(
            select(func.count()).select_from(Hold).where(Hold.promo_code_id == code.id)
        )
        assert code.used_count + reserved <= code.max_uses
    check_stock(committed)
