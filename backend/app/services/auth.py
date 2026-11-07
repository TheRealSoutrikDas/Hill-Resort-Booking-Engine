"""Accounts and sign-in sessions (A-70 to A-78, D-33).

A session is a random token in an HttpOnly cookie; the database keeps only its SHA-256
hash. Every login starts a new session (no session fixation) and logout deletes it, so
a stolen cookie stops working at once. Functions take a Session and never commit.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User, UserSession
from app.db.models.enums import UserRole
from app.services import passwords
from app.services.errors import EmailTaken, InvalidCredentials, InvalidSignup
from app.services.validation import (
    is_valid_email,
    is_valid_name,
    is_valid_phone,
    normalize_email,
    normalize_name,
    normalize_phone,
)

# The version of the consent text shown on the sign-up form; stored with each account.
SIGNUP_CONSENT_VERSION = "signup-v1"
TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class NewSession:
    token: str  # goes in the cookie; never stored
    record: UserSession


def sign_up(
    session: Session,
    *,
    full_name: str,
    email: str,
    password: str,
    phone: str | None,
    consent: bool,
    now: datetime,
) -> User:
    """Create a guest account. Public sign-up never creates staff (A-75)."""
    full_name, email = normalize_name(full_name), normalize_email(email)
    phone = normalize_phone(phone) if phone and phone.strip() else None
    if not consent:
        raise InvalidSignup("consent_required", "Please agree to how we use your details.")
    if not is_valid_name(full_name):
        raise InvalidSignup("invalid_name", "Enter your name.")
    if not is_valid_email(email):
        raise InvalidSignup("invalid_email", "Enter a valid email address.")
    if phone is not None and not is_valid_phone(phone):
        raise InvalidSignup("invalid_phone", "Enter a valid phone number.")
    if not passwords.is_acceptable(password):
        raise InvalidSignup(
            "weak_password",
            f"Use a password of {passwords.MIN_LENGTH} to {passwords.MAX_LENGTH} characters.",
        )

    user = User(
        email=email,
        password_hash=passwords.hash_password(password),
        full_name=full_name,
        phone=phone,
        role=UserRole.GUEST,
        consent_at=now,
        consent_version=SIGNUP_CONSENT_VERSION,
        created_at=now,
    )
    try:
        with session.begin_nested():
            session.add(user)
            session.flush()
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_users_email":
            raise EmailTaken("An account with this email exists. Log in instead.") from exc
        raise
    return user


def authenticate(session: Session, *, email: str, password: str) -> User:
    """The account for these credentials, or InvalidCredentials with one message for a
    wrong email and a wrong password, taking the same time for both (A-76)."""
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        passwords.spend_verify_time(password)
        raise InvalidCredentials("Email or password is incorrect.")
    if not passwords.verify_password(user.password_hash, password):
        raise InvalidCredentials("Email or password is incorrect.")
    if passwords.needs_rehash(user.password_hash):  # parameters were raised: upgrade
        user.password_hash = passwords.hash_password(password)
    return user


def start_session(session: Session, user: User, *, now: datetime, ttl_hours: int) -> NewSession:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    record = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(TOKEN_BYTES),
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    session.add(record)
    session.flush()
    return NewSession(token=token, record=record)


def find_session(session: Session, token: str | None, *, now: datetime) -> UserSession | None:
    """The live session for a cookie token, or None (missing, unknown or expired)."""
    if not token:
        return None
    return session.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token), UserSession.expires_at > now
        )
    )


def end_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
