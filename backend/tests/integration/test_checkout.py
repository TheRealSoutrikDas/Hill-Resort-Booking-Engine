"""Paying for a hold through the mock gateway, and refunds (A-59 to A-63, D-31).

Checkout commits its own transactions, so these tests use committed sessions."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Allotment, Booking, Hold, Payment
from app.services.bookings import HOLD_EXPIRED_SOLD_OUT
from app.services.checkout import (
    CONFIRMED,
    DECLINED,
    REFUND_PENDING,
    REFUNDED,
    TIMED_OUT,
    cancel_and_refund,
    pay_for_hold,
    process_refund,
)
from app.services.errors import HoldNotActive, HoldNotFound, PaymentNotAllowed
from app.services.holds import create_hold, set_guest_details
from app.services.payments.mock import MockPaymentProvider
from app.services.payments.provider import ProviderError
from app.services.references import is_valid_booking_reference
from tests.factories import NOW, RULES, catalogue, guest, line, request

LATER = NOW + timedelta(minutes=11)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def key() -> str:
    return uuid.uuid4().hex


def ready_hold(committed: sessionmaker[Session], dlx_web: int = 4, details: bool = True):
    """Returns (user id, hold id, request) for a hold made at NOW."""
    with committed() as s, s.begin():
        c = catalogue(s, dlx_web=dlx_web)
        user_id, req = c.user.id, request(line(c.dlx, c.ro))
    with committed() as s, s.begin():
        hold_id = create_hold(s, user_id, req, now=NOW, rules=RULES).hold_id
        if details:
            set_guest_details(
                s,
                user_id,
                hold_id,
                name="Asha Rao",
                email="asha@example.com",
                phone="+91 00000 00042",
                now=NOW,
            )
    return user_id, hold_id, req


def pay(committed, provider, user_id, hold_id, idem: str, simulate="success", clock=None):
    return pay_for_hold(
        committed,
        provider,
        user_id,
        hold_id,
        idem,
        rules=RULES,
        simulate=simulate,
        clock=clock or FakeClock(NOW),
    )


def rows(committed, model, *where) -> int:
    with committed() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def payment_status(committed, payment_id: int) -> str:
    with committed() as s:
        return s.get(Payment, payment_id).status


# ---------- outcomes ----------


def test_success_confirms_the_booking(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed)

    result = pay(committed, provider, user_id, hold_id, key())

    assert result.status == CONFIRMED and is_valid_booking_reference(result.booking_reference)
    with committed() as s:
        payment = s.get(Payment, result.payment_id)
        assert payment.status == "succeeded" and payment.provider_reference.startswith("MOCK-")
        assert s.scalars(select(Allotment.sold).where(Allotment.sold > 0)).all() == [1, 1]
    assert provider.captured_count == 1


@pytest.mark.parametrize(
    ("simulate", "status", "db_status"),
    [("decline", DECLINED, "failed"), ("timeout", TIMED_OUT, "timed_out")],
)
def test_decline_or_timeout_keeps_the_hold_for_another_try(
    committed, simulate, status, db_status
) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed)

    first = pay(committed, provider, user_id, hold_id, key(), simulate=simulate)
    assert first.status == status and payment_status(committed, first.payment_id) == db_status
    with committed() as s:
        assert s.get(Hold, hold_id).status == "active"

    retry = pay(committed, provider, user_id, hold_id, key())  # a new click, a new key
    assert retry.status == CONFIRMED and provider.captured_count == 1


def test_unexpected_gateway_error_counts_as_a_timeout(committed) -> None:
    class Broken(MockPaymentProvider):
        def charge(self, **kwargs):
            raise ConnectionError("gateway unreachable")

    user_id, hold_id, _ = ready_hold(committed)
    result = pay(committed, Broken(), user_id, hold_id, key())
    assert (
        result.status == TIMED_OUT and payment_status(committed, result.payment_id) == "timed_out"
    )


# ---------- idempotency (A-61) ----------


def test_same_key_twice_returns_the_same_booking_and_charges_once(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed)
    idem = key()
    first = pay(committed, provider, user_id, hold_id, idem)
    again = pay(committed, provider, user_id, hold_id, idem)
    assert again == first
    assert provider.captured_count == 1 and rows(committed, Payment) == 1


def test_declined_key_stays_declined(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed)
    idem = key()
    pay(committed, provider, user_id, hold_id, idem, simulate="decline")
    assert pay(committed, provider, user_id, hold_id, idem).status == DECLINED
    assert provider.captured_count == 0


def test_key_reused_for_another_hold_is_refused(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, req = ready_hold(committed)
    idem = key()
    pay(committed, provider, user_id, hold_id, idem, simulate="decline")
    with committed() as s, s.begin():
        other = create_hold(s, user_id, req, now=NOW, rules=RULES).hold_id
    with pytest.raises(PaymentNotAllowed) as err:
        pay(committed, provider, user_id, other, idem)
    assert err.value.code == "idempotency_key_reused"


def test_too_short_key_is_refused(committed) -> None:
    user_id, hold_id, _ = ready_hold(committed)
    with pytest.raises(PaymentNotAllowed) as err:
        pay(committed, MockPaymentProvider(), user_id, hold_id, "short")
    assert err.value.code == "invalid_idempotency_key"


# ---------- refused before any money moves (A-60) ----------


def test_missing_guest_details_refused_before_charging(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed, details=False)
    with pytest.raises(PaymentNotAllowed) as err:
        pay(committed, provider, user_id, hold_id, key())
    assert err.value.code == "guest_details_missing"
    assert rows(committed, Payment) == 0 and provider.captured_count == 0


def test_expired_hold_refused_before_charging(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed)
    with pytest.raises(HoldNotActive) as err:
        pay(committed, provider, user_id, hold_id, key(), clock=FakeClock(LATER))
    assert err.value.code == "hold_expired"
    assert rows(committed, Payment) == 0 and provider.captured_count == 0


def test_another_account_cannot_pay(committed) -> None:
    provider = MockPaymentProvider()
    _, hold_id, _ = ready_hold(committed)
    with committed() as s, s.begin():
        stranger = guest(s).id
    with pytest.raises(HoldNotFound):
        pay(committed, provider, stranger, hold_id, key())
    assert rows(committed, Payment) == 0


# ---------- the brief's case: the hold expires during the charge ----------


def test_hold_expires_during_charge_and_stock_is_taken_so_money_is_refunded(committed) -> None:
    clock = FakeClock(NOW)
    user_id, hold_id, req = ready_hold(committed, dlx_web=1)
    with committed() as s, s.begin():
        rival = guest(s).id

    def meanwhile() -> None:  # the gateway is slow; the hold expires; someone else books
        clock.now = LATER
        with committed() as s, s.begin():
            create_hold(s, rival, req, now=LATER, rules=RULES)

    provider = MockPaymentProvider(on_charge=meanwhile)
    result = pay(committed, provider, user_id, hold_id, key(), clock=clock)

    assert (result.status, result.failure) == (REFUNDED, HOLD_EXPIRED_SOLD_OUT)
    with committed() as s:
        payment = s.get(Payment, result.payment_id)
        assert payment.status == "refunded" and provider.was_refunded(payment.provider_reference)
    assert rows(committed, Booking) == 0


def test_hold_expires_during_charge_but_stock_is_free_so_booking_is_confirmed(committed) -> None:
    clock = FakeClock(NOW)
    user_id, hold_id, _ = ready_hold(committed)

    def slow_gateway() -> None:
        clock.now = LATER

    result = pay(
        committed, MockPaymentProvider(on_charge=slow_gateway), user_id, hold_id, key(), clock=clock
    )
    assert result.status == CONFIRMED


# ---------- refunds (A-63) ----------


def test_cancel_refunds_the_payment_and_repeating_is_harmless(committed) -> None:
    provider = MockPaymentProvider()
    user_id, hold_id, _ = ready_hold(committed)
    booked = pay(committed, provider, user_id, hold_id, key())

    assert (
        cancel_and_refund(
            committed,
            provider,
            user_id,
            booked.booking_reference,
            rules=RULES,
            clock=FakeClock(NOW),
        )
        == REFUNDED
    )
    assert (
        cancel_and_refund(
            committed,
            provider,
            user_id,
            booked.booking_reference,
            rules=RULES,
            clock=FakeClock(NOW),
        )
        == REFUNDED
    )
    with committed() as s:
        payment = s.get(Payment, booked.payment_id)
        assert payment.status == "refunded" and provider.was_refunded(payment.provider_reference)
        assert s.scalars(select(Allotment.sold)).all() == [0, 0, 0, 0]


def test_failed_refund_stays_pending_and_can_be_retried(committed) -> None:
    class FlakyRefunds(MockPaymentProvider):
        fail_next = True

        def refund(self, **kwargs) -> None:
            if self.fail_next:
                self.fail_next = False
                raise ProviderError("gateway busy")
            super().refund(**kwargs)

    provider = FlakyRefunds()
    user_id, hold_id, _ = ready_hold(committed)
    booked = pay(committed, provider, user_id, hold_id, key())

    assert (
        cancel_and_refund(
            committed,
            provider,
            user_id,
            booked.booking_reference,
            rules=RULES,
            clock=FakeClock(NOW),
        )
        == REFUND_PENDING
    )
    assert payment_status(committed, booked.payment_id) == "refund_pending"
    assert process_refund(committed, provider, booked.payment_id, clock=FakeClock(NOW)) == REFUNDED
    assert payment_status(committed, booked.payment_id) == "refunded"
