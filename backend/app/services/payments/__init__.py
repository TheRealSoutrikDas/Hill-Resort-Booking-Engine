"""Payment gateway adapters, selected by the PAYMENT_PROVIDER setting."""

from functools import lru_cache

from app.core.config import Settings
from app.services.payments.mock import MockPaymentProvider
from app.services.payments.provider import PaymentProvider


@lru_cache
def _mock() -> MockPaymentProvider:
    # One instance per process, so its idempotency memory is shared by all requests.
    return MockPaymentProvider()


def get_payment_provider(settings: Settings) -> PaymentProvider:
    if settings.payment_provider == "mock":
        return _mock()
    raise ValueError(f"unknown payment provider: {settings.payment_provider}")
