"""The payment gateway interface. The mock implements it; a real gateway (Razorpay,
Stripe) would be a second implementation and nothing else would change (D-31)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

# What the guest picks on the test-mode payment step (A-59). Real gateways ignore it.
SimulatedOutcome = Literal["success", "decline", "timeout"]


class ChargeStatus(StrEnum):
    CAPTURED = "captured"
    DECLINED = "declined"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ChargeResult:
    status: ChargeStatus
    provider_reference: str | None = None


class ProviderError(Exception):
    """The gateway could not complete a call (for example a refund). Safe to retry."""


class PaymentProvider(Protocol):
    name: str

    def charge(
        self, *, amount_paise: int, idempotency_key: str, simulate: SimulatedOutcome = "success"
    ) -> ChargeResult:
        """Charge once per idempotency key: repeating a key returns the first result."""
        ...

    def refund(self, *, provider_reference: str, amount_paise: int) -> None:
        """Refund a captured charge in full. Repeating it is harmless."""
        ...
