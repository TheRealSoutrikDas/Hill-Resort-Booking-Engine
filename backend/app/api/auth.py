"""Sign-up, login, logout and the current user (A-75 to A-77)."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import AppSettings, DbSession
from app.api.errors import ErrorResponse
from app.api.ratelimit import LoginFailures, limit_per_ip
from app.api.security import (
    SESSION_COOKIE,
    CurrentUser,
    clear_session_cookie,
    current_session,
    set_session_cookie,
)
from app.core.clock import utc_now
from app.db.models import User
from app.services import auth as auth_service
from app.services.errors import InvalidCredentials, NotAuthenticated

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupIn(BaseModel):
    # extra="forbid": a request cannot sneak in a role, team or GM flag.
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=200)
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)
    phone: str | None = Field(default=None, max_length=40)
    consent: bool


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class Me(BaseModel):
    """The signed-in account, plus the CSRF token the frontend must send back."""

    id: int
    full_name: str
    email: str
    phone: str | None
    role: str
    team: str | None
    is_gm: bool
    csrf_token: str


def _me(user: User, csrf_token: str) -> Me:
    return Me(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        team=user.team,
        is_gm=user.is_gm,
        csrf_token=csrf_token,
    )


def _start(request: Request, response: Response, db: DbSession, user: User, settings) -> Me:
    # A new session at every sign-in (no session fixation); any old one is ended.
    auth_service.end_session(db, request.cookies.get(SESSION_COOKIE))
    new = auth_service.start_session(db, user, now=utc_now(), ttl_hours=settings.session_ttl_hours)
    set_session_cookie(response, new.token, settings)
    return _me(user, new.record.csrf_token)


@router.post(
    "/signup",
    status_code=201,
    response_model=Me,
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    dependencies=[Depends(limit_per_ip("signup"))],
)
def signup(
    body: SignupIn, request: Request, response: Response, db: DbSession, settings: AppSettings
) -> Me:
    """Create a guest account and sign in. Public sign-up never creates staff."""
    user = auth_service.sign_up(
        db,
        full_name=body.full_name,
        email=body.email,
        password=body.password,
        phone=body.phone,
        consent=body.consent,
        now=utc_now(),
    )
    return _start(request, response, db, user, settings)


@router.post(
    "/login",
    response_model=Me,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_ip("login"))],
)
def login(
    body: LoginIn, request: Request, response: Response, db: DbSession, settings: AppSettings
) -> Me:
    """One error for a wrong email or a wrong password. Five failures for one email
    lock it for a while, even from different IPs (A-80)."""
    failures = LoginFailures(request, body.email)
    failures.check()  # before verifying, so a locked email cannot be guessed at all
    try:
        user = auth_service.authenticate(db, email=body.email, password=body.password)
    except InvalidCredentials:
        failures.failed()
        raise
    failures.succeeded()
    return _start(request, response, db, user, settings)


@router.post("/logout", status_code=204, responses={401: {"model": ErrorResponse}})
def logout(
    user: CurrentUser, request: Request, response: Response, db: DbSession, settings: AppSettings
) -> None:
    """Delete the session, so the cookie stops working everywhere at once."""
    auth_service.end_session(db, request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response, settings)


@router.get("/me", response_model=Me, responses={401: {"model": ErrorResponse}})
def me(request: Request, db: DbSession) -> Me:
    """Who is signed in, for redirects by role and the CSRF token (A-74)."""
    record = current_session(request, db)
    if record is None:
        raise NotAuthenticated("Please log in.")
    return _me(db.get(User, record.user_id), record.csrf_token)
