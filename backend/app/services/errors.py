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
