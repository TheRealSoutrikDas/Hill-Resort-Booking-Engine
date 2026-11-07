import pytest

from app.services.payments.mock import MockPaymentProvider
from app.services.payments.provider import ChargeStatus


def test_success_captures_with_a_reference() -> None:
    provider = MockPaymentProvider()
    result = provider.charge(amount_paise=100, idempotency_key="key-00000001")
    assert result.status == ChargeStatus.CAPTURED
    assert result.provider_reference.startswith("MOCK-")
    assert provider.captured_count == 1


@pytest.mark.parametrize(("simulate", "status"), [("decline", "declined"), ("timeout", "timeout")])
def test_failures_capture_nothing(simulate: str, status: str) -> None:
    provider = MockPaymentProvider()
    result = provider.charge(amount_paise=100, idempotency_key="key-00000001", simulate=simulate)
    assert (result.status, result.provider_reference) == (status, None)
    assert provider.captured_count == 0


def test_same_key_returns_the_first_result_and_charges_once() -> None:
    provider = MockPaymentProvider()
    first = provider.charge(amount_paise=100, idempotency_key="key-00000001")
    again = provider.charge(amount_paise=100, idempotency_key="key-00000001", simulate="decline")
    assert again == first and provider.captured_count == 1


def test_a_declined_key_stays_declined() -> None:
    provider = MockPaymentProvider()
    provider.charge(amount_paise=100, idempotency_key="key-00000001", simulate="decline")
    assert provider.charge(amount_paise=100, idempotency_key="key-00000001").status == "declined"


def test_different_keys_are_separate_charges() -> None:
    provider = MockPaymentProvider()
    a = provider.charge(amount_paise=100, idempotency_key="key-00000001")
    b = provider.charge(amount_paise=100, idempotency_key="key-00000002")
    assert a.provider_reference != b.provider_reference and provider.captured_count == 2


@pytest.mark.parametrize(("amount", "simulate"), [(0, "success"), (100, "maybe")])
def test_rejects_bad_input(amount: int, simulate: str) -> None:
    with pytest.raises(ValueError):
        MockPaymentProvider().charge(
            amount_paise=amount, idempotency_key="key-00000001", simulate=simulate
        )


def test_refund_is_recorded_and_harmless_twice() -> None:
    provider = MockPaymentProvider()
    reference = provider.charge(amount_paise=100, idempotency_key="key-00000001").provider_reference
    provider.refund(provider_reference=reference, amount_paise=100)
    provider.refund(provider_reference=reference, amount_paise=100)
    assert provider.was_refunded(reference)
