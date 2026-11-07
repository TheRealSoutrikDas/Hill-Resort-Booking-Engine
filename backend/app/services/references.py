"""Booking reference generation (docs/DECISIONS.md D-14).

References are random, not derived from the booking id, so they cannot be guessed;
booking lookup is by reference plus email. Uniqueness is guaranteed by the UNIQUE
constraint on bookings.reference: the booking service generates a new reference and
retries when an insert collides, up to MAX_REFERENCE_ATTEMPTS times.
"""

import random
import re
import secrets

from app.db.models.booking import BOOKING_REFERENCE_ALPHABET, BOOKING_REFERENCE_LENGTH

BOOKING_REFERENCE_PREFIX = "BK-"
MAX_REFERENCE_ATTEMPTS = 5

_REFERENCE_RE = re.compile(
    rf"^{BOOKING_REFERENCE_PREFIX}[{BOOKING_REFERENCE_ALPHABET}]{{{BOOKING_REFERENCE_LENGTH}}}$"
)


def generate_booking_reference(rng: random.Random | None = None) -> str:
    """A new reference such as BK-7F3K9QXM.

    Production passes no rng and gets cryptographically random codes. The seed script
    passes a seeded random.Random so its references are the same on every run.
    """
    choose = rng.choice if rng is not None else secrets.choice
    body = "".join(choose(BOOKING_REFERENCE_ALPHABET) for _ in range(BOOKING_REFERENCE_LENGTH))
    return BOOKING_REFERENCE_PREFIX + body


def normalize_booking_reference(value: str) -> str:
    """Trim and uppercase what a guest typed, so 'bk-7f3k9qxm ' still matches."""
    return value.strip().upper()


def is_valid_booking_reference(value: str) -> bool:
    """Format check before any database lookup."""
    return bool(_REFERENCE_RE.fullmatch(value))
