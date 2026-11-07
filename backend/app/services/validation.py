"""Shape checks for personal details, shared by sign-up and booking guest details
(A-49). Shape only: an email address is never verified (brief)."""

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 ]{6,18}[0-9]$")


def normalize_name(value: str) -> str:
    return value.strip()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return " ".join(value.split())


def is_valid_name(name: str) -> bool:
    return 1 <= len(name) <= 120


def is_valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(_EMAIL_RE.fullmatch(email))


def is_valid_phone(phone: str) -> bool:
    return len(phone) <= 20 and bool(_PHONE_RE.fullmatch(phone))
