"""Pay for a hold, and complete refunds (D-31).

The gateway is never called inside a database transaction: a slow network call must
not hold row locks while other guests wait. So paying runs as three short transactions:

1. start: check the hold, record a `pending` payment with the idempotency key, commit;
2. charge the gateway, outside any transaction;
3. record the result: captured goes to `confirm_booking` (step 6), declined becomes
   `failed`, timeout becomes `timed_out`.

Because of that, these functions take a session factory and manage their own
transactions, unlike the other services, which leave committing to the caller.

A double click sends the same idempotency key twice. The second request finds the
first payment and returns its result instead of charging again (A-61).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utc_now
from app.db.models import Booking, Payment
from app.db.models.enums import PaymentStatus
from app.services.bookings import cancel_booking, confirm_booking
from app.services.errors import PaymentNotAllowed, StockLocked
from app.services.holds import HoldRules, get_owned_hold, require_active
from app.services.payments.provider import (
    ChargeStatus,
    PaymentProvider,
    ProviderError,
    SimulatedOutcome,
)

# Statuses a checkout reports to the guest.
CONFIRMED = "confirmed"
DECLINED = "declined"
TIMED_OUT = "timed_out"
PROCESSING = "processing"  # another request with the same key has not finished yet
REFUNDED = "refunded"  # money was taken but no booking could be made; it was returned
REFUND_PENDING = "refund_pending"  # as above, but the refund call has not succeeded yet

CONFIRM_ATTEMPTS = 3  # retries when recording a captured payment meets a lock timeout

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CheckoutResult:
    status: str
    payment_id: int
    booking_reference: str | None = None
    failure: str | None = None  # why a captured payment was refunded, if known


def _result_for(session: Session, payment: Payment) -> CheckoutResult:
    """Report an existing payment's state (used for repeated idempotency keys)."""
    if payment.status == PaymentStatus.SUCCEEDED:
        booking = session.scalar(select(Booking).where(Booking.payment_id == payment.id))
        return CheckoutResult(CONFIRMED, payment.id, booking.reference if booking else None)
    status = {
        PaymentStatus.PENDING: PROCESSING,
        PaymentStatus.FAILED: DECLINED,
        PaymentStatus.TIMED_OUT: TIMED_OUT,
        PaymentStatus.REFUND_PENDING: REFUND_PENDING,
        PaymentStatus.REFUNDED: REFUNDED,
    }[PaymentStatus(payment.status)]
    return CheckoutResult(status, payment.id)


def _start(
    factory: sessionmaker[Session],
    provider: PaymentProvider,
    user_id: int,
    hold_id: UUID,
    idempotency_key: str,
    now: datetime,
) -> tuple[tuple[int, int] | None, CheckoutResult | None]:
    """Transaction 1. Returns the new pending payment's (id, amount), or the result of
    an earlier request with the same key. Plain values, so nothing depends on the
    closed session."""
    with factory() as session, session.begin():
        # Locking the hold first makes a second request with the same key wait for the
        # first to commit, so the lookup below then finds its payment.
        hold = get_owned_hold(session, user_id, hold_id, lock=True)
        existing = session.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.hold_id != hold.id:
                raise PaymentNotAllowed("idempotency_key_reused", "Please start the payment again.")
            return None, _result_for(session, existing)
        require_active(hold, now)  # A-60: expired, released or paid holds cannot start
        if not (hold.guest_name and hold.guest_email and hold.guest_phone):
            raise PaymentNotAllowed(
                "guest_details_missing", "Please add the guest's details first."
            )
        payment = Payment(
            hold_id=hold.id,
            idempotency_key=idempotency_key,
            provider=provider.name,
            amount_paise=hold.total_paise,
            status=PaymentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        session.add(payment)
        session.flush()
        return (payment.id, payment.amount_paise), None


def pay_for_hold(
    factory: sessionmaker[Session],
    provider: PaymentProvider,
    user_id: int,
    hold_id: UUID,
    idempotency_key: str,
    *,
    rules: HoldRules,
    simulate: SimulatedOutcome = "success",
    clock: Clock = utc_now,
) -> CheckoutResult:
    """Charge the hold's total and confirm the booking.

    Raises before any money moves (nothing saved): HoldNotFound, HoldNotActive,
    PaymentNotAllowed. After money moves, every outcome is returned, not raised.
    """
    if not 8 <= len(idempotency_key) <= 64:
        raise PaymentNotAllowed("invalid_idempotency_key", "Please start the payment again.")
    try:
        started, earlier = _start(factory, provider, user_id, hold_id, idempotency_key, clock())
    except IntegrityError:
        # Two requests with one key raced past the lookup; report the winner's payment.
        with factory() as session:
            existing = session.scalar(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            return _result_for(session, existing)
    if earlier is not None:
        return earlier
    payment_id, amount_paise = started

    # 2. The gateway call, outside any transaction.
    try:
        charge = provider.charge(
            amount_paise=amount_paise, idempotency_key=idempotency_key, simulate=simulate
        )
    except Exception:  # an unexpected gateway error is treated as a timeout (A-62)
        charge = None

    # 3. Record the result.
    if charge is None or charge.status != ChargeStatus.CAPTURED:
        status = (
            PaymentStatus.FAILED
            if charge and charge.status == ChargeStatus.DECLINED
            else PaymentStatus.TIMED_OUT
        )
        with factory() as session, session.begin():
            row = session.get(Payment, payment_id, with_for_update=True)
            row.status, row.updated_at = status, clock()
        return CheckoutResult(DECLINED if status == PaymentStatus.FAILED else TIMED_OUT, payment_id)

    for attempt in range(CONFIRM_ATTEMPTS):
        try:
            with factory() as session, session.begin():
                row = session.get(Payment, payment_id)
                row.provider_reference = charge.provider_reference
                session.flush()
                outcome = confirm_booking(
                    session, user_id, hold_id, payment_id, now=clock(), rules=rules
                )
                reference = outcome.booking.reference if outcome.booking else None
            break
        except StockLocked:
            # The money is taken: keep trying to record it. If every attempt times out,
            # the payment stays `pending` with the gateway holding the money; a real
            # system would settle it from the gateway's records (D-31).
            if attempt == CONFIRM_ATTEMPTS - 1:
                return CheckoutResult(PROCESSING, payment_id)

    if outcome.confirmed:
        return CheckoutResult(CONFIRMED, payment_id, reference)
    status = process_refund(factory, provider, payment_id, clock=clock)
    return CheckoutResult(status, payment_id, failure=outcome.failure)


def process_refund(
    factory: sessionmaker[Session],
    provider: PaymentProvider,
    payment_id: int,
    *,
    clock: Clock = utc_now,
) -> str:
    """Send a `refund_pending` payment's refund to the gateway and mark it `refunded`.

    Harmless to repeat. If the gateway call fails, the payment stays `refund_pending`
    so the refund can be retried (A-63). Returns the payment's resulting status.
    """
    with factory() as session:
        payment = session.get(Payment, payment_id)
        if payment.status == PaymentStatus.REFUNDED:
            return REFUNDED
        if payment.status != PaymentStatus.REFUND_PENDING:
            raise ValueError(f"payment {payment_id} is {payment.status}, not refund_pending")
        reference, amount = payment.provider_reference, payment.amount_paise
    if reference is None:
        return REFUND_PENDING  # nothing was captured at the gateway to refund
    try:
        provider.refund(provider_reference=reference, amount_paise=amount)
    except ProviderError:
        return REFUND_PENDING
    with factory() as session, session.begin():
        payment = session.get(Payment, payment_id, with_for_update=True)
        if payment.status == PaymentStatus.REFUND_PENDING:
            payment.status, payment.updated_at = PaymentStatus.REFUNDED, clock()
    return REFUNDED


def cancel_and_refund(
    factory: sessionmaker[Session],
    provider: PaymentProvider,
    user_id: int,
    reference: str,
    *,
    rules: HoldRules,
    clock: Clock = utc_now,
) -> str:
    """Cancel a booking (stock back, payment marked for refund), commit, then refund."""
    with factory() as session, session.begin():
        booking = cancel_booking(session, user_id, reference, now=clock(), rules=rules)
        payment_id = booking.payment_id
    return process_refund(factory, provider, payment_id, clock=clock)
