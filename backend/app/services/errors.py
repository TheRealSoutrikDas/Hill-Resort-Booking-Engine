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
