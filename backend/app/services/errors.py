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


class RateLimited(DomainError):
    """Too many attempts. `retry_after` is how many seconds to wait."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many attempts. Please wait a little and try again.")
        self.retry_after = retry_after


class RoomTypeNotFound(DomainError):
    """No room type with this code."""


class InvalidAdminChange(DomainError):
    """An admin change breaks a rule (dates, ranges, units). `code` says which."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AllotmentTooLow(DomainError):
    """The new web allotment would be below what is sold or held on some nights (A-102)."""

    def __init__(self, nights: list[dict]) -> None:
        super().__init__("The allotment cannot go below what is already sold or held.")
        self.nights = nights


class BlackoutBlocked(DomainError):
    """Guests are holding rooms on some of these nights; try again shortly (A-103)."""

    def __init__(self, nights: list[dict]) -> None:
        super().__init__(
            "Guests are in checkout on some of these nights. Try again in a few minutes."
        )
        self.nights = nights


class PromoNotFound(DomainError):
    """No promo code with this code."""


class PromoCodeTaken(DomainError):
    """A promo code with this code already exists."""


class PromoCapTooLow(DomainError):
    """The usage cap would be below uses already counted plus uses reserved by holds (A-105)."""

    def __init__(self, used: int, reserved: int) -> None:
        super().__init__("The cap cannot go below uses already made or reserved.")
        self.used, self.reserved = used, reserved


class InvalidEnquiry(DomainError):
    """The enquiry form breaks a rule (A-114). `code` says which."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
