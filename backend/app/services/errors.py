"""Domain errors raised by services. The API layer maps them to HTTP responses."""

from dataclasses import dataclass
from datetime import date


class DomainError(Exception):
    """Base class for expected, user-facing failures (not bugs)."""


class InvalidStay(DomainError):
    """The requested dates break a booking rule. `code` is stable for API clients."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Shortfall:
    room_type_id: int
    stay_date: date
    requested: int
    available: int


class NotAvailable(DomainError):
    """At least one room type is short on at least one night."""

    def __init__(self, shortfalls: list[Shortfall]) -> None:
        super().__init__(f"{len(shortfalls)} night(s) without enough rooms")
        self.shortfalls = tuple(shortfalls)


class StockLocked(DomainError):
    """Another booking held the stock lock past the timeout. Safe to retry.

    The current transaction is aborted and must be rolled back.
    """


class InvalidBookingRequest(DomainError):
    """The requested rooms, guests or rates break a booking rule. `code` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class HoldNotFound(DomainError):
    """No such hold for this account. Also raised for another account's hold, so a
    hold id never reveals that someone else's hold exists (A-43)."""


class HoldNotActive(DomainError):
    """The hold expired, was released or was already paid. `code` says which."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PaymentMismatch(DomainError):
    """The payment does not belong to this hold, or was never captured. `code` says which."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BookingNotFound(DomainError):
    """No such booking for this account. Also raised for another account's booking."""


class CancellationNotAllowed(DomainError):
    """The booking can no longer be cancelled online. `code` says why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InvalidPromoCode(DomainError):
    """The promo code cannot be used. `code` says why (A-58: being specific is fine,
    promo codes are not secrets)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PaymentNotAllowed(DomainError):
    """A payment cannot start (for example guest details are missing). `code` says why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NotAuthenticated(DomainError):
    """No valid session: the caller must sign in."""


class Forbidden(DomainError):
    """Signed in, but this account may not do this."""


class CsrfFailed(DomainError):
    """A state-changing request without a valid CSRF token or from a foreign origin."""


class InvalidCredentials(DomainError):
    """Wrong email or wrong password: one error for both (A-76)."""


class EmailTaken(DomainError):
    """An account with this email already exists (A-75)."""


class InvalidSignup(DomainError):
    """Sign-up details break a rule. `code` says which."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
