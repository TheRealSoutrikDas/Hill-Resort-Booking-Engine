"""Password hashing with argon2id (A-70, A-71).

`argon2-cffi`'s defaults follow RFC 9106's recommended profile. Hashing is deliberately
slow (about 170 ms here); that is what makes stolen hashes expensive to crack. Tests
swap in a cheap hasher with `use_hasher` so the suite stays fast (D-33).
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 10
MAX_LENGTH = 128

_hasher = PasswordHasher()
_dummy_hash: str | None = None


def use_hasher(hasher: PasswordHasher) -> None:
    """Replace the hasher (tests only: production keeps the library defaults)."""
    global _hasher, _dummy_hash
    _hasher, _dummy_hash = hasher, None


def is_acceptable(password: str) -> bool:
    """Length only, no composition rules (NIST SP 800-63B)."""
    return MIN_LENGTH <= len(password) <= MAX_LENGTH


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """False for a wrong password and for anything that is not a valid hash, such as
    the unusable marker on accounts that cannot log in."""
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True when the hash was made with weaker parameters than the current ones."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False


def spend_verify_time(password: str) -> None:
    """Do the work of a real verification against a dummy hash, so a login for an email
    with no account takes as long as one for a real account (A-76)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash("dummy password for timing")
    verify_password(_dummy_hash, password)
