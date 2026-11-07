"""A simulated gateway for test mode (brief: real payments are simulated).

Like a real gateway it remembers each idempotency key, so charging the same key twice
returns the first result and never charges twice. The memory lives in this process,
which is fine for a mock; with several server instances each would have its own (D-31).

A mock timeout means "not charged". A real gateway's timeout means "unknown", and a
real integration must ask the gateway what happened to the key before retrying (A-62).
"""

import hashlib
import threading
from collections.abc import Callable

from app.services.payments.provider import ChargeResult, ChargeStatus, SimulatedOutcome

_OUTCOMES = {
    "success": ChargeStatus.CAPTURED,
    "decline": ChargeStatus.DECLINED,
    "timeout": ChargeStatus.TIMEOUT,
}


class MockPaymentProvider:
    name = "mock"

    def __init__(self, on_charge: Callable[[], None] | None = None) -> None:
        # on_charge runs while a new charge is "processing": tests use it to make things
        # happen during the network call, such as the hold expiring.
        self._on_charge = on_charge
        self._charges: dict[str, ChargeResult] = {}
        self._refunded: set[str] = set()
        self._lock = threading.Lock()
        self.captured_count = 0  # real money movements, for tests

    def charge(
        self, *, amount_paise: int, idempotency_key: str, simulate: SimulatedOutcome = "success"
    ) -> ChargeResult:
        if amount_paise <= 0:
            raise ValueError("amount must be positive")
        if simulate not in _OUTCOMES:
            raise ValueError(f"unknown simulated outcome: {simulate}")
        with self._lock:  # one key is processed once, like a gateway's idempotency
            if idempotency_key in self._charges:
                return self._charges[idempotency_key]
            if self._on_charge is not None:
                self._on_charge()
            status = _OUTCOMES[simulate]
            reference = None
            if status == ChargeStatus.CAPTURED:
                digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12].upper()
                reference = f"MOCK-{digest}"
                self.captured_count += 1
            result = ChargeResult(status, reference)
            self._charges[idempotency_key] = result
            return result

    def refund(self, *, provider_reference: str, amount_paise: int) -> None:
        with self._lock:
            self._refunded.add(provider_reference)

    def was_refunded(self, provider_reference: str) -> bool:
        return provider_reference in self._refunded
