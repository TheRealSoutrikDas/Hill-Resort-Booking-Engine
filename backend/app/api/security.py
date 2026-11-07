"""Who is calling, and may they? (A-72 to A-74, A-77, D-33)

`require_user(...)` is the one dependency every protected route uses. It finds the
session from the cookie, checks the CSRF token on state-changing requests, and checks
role, team and GM flag. Not signed in is 401; signed in but not allowed is 403.
"""

import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.deps import DbSession
from app.api.errors import error_response
from app.core.clock import utc_now
from app.core.config import Settings
from app.db.models import User, UserSession
from app.services.auth import find_session
from app.services.errors import CsrfFailed, Forbidden, NotAuthenticated

SESSION_COOKIE = "session"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


def current_session(request: Request, db: DbSession) -> UserSession | None:
    return find_session(db, request.cookies.get(SESSION_COOKIE), now=utc_now())


def require_user(
    *, role: str | None = None, team: str | None = None, gm: bool = False
) -> Callable[..., User]:
    """Build a dependency that returns the signed-in user if they meet the requirement.

    `team` admits staff of that team, and the GM. `gm=True` admits only the GM."""

    def dependency(
        request: Request,
        db: DbSession,
        record: Annotated[UserSession | None, Depends(current_session)],
    ) -> User:
        if record is None:
            raise NotAuthenticated("Please log in.")
        if request.method in UNSAFE_METHODS:
            sent = request.headers.get(CSRF_HEADER, "")
            if not hmac.compare_digest(sent.encode(), record.csrf_token.encode()):
                raise CsrfFailed("Your session needs refreshing. Please reload the page.")
        user = db.get(User, record.user_id)
        if role is not None and user.role != role:
            raise Forbidden("This account cannot do that.")
        if team is not None and not user.is_gm and user.team != team:
            raise Forbidden("This account cannot do that.")
        if gm and not user.is_gm:
            raise Forbidden("This account cannot do that.")
        return user

    return dependency


CurrentUser = Annotated[User, Depends(require_user())]
GuestUser = Annotated[User, Depends(require_user(role="guest"))]
StaffUser = Annotated[User, Depends(require_user(role="staff"))]
GmUser = Annotated[User, Depends(require_user(role="staff", gm=True))]


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Refuse state-changing requests whose Origin is not one of ours (A-74, layer 2).

    Browsers always send Origin on these requests; through the Next.js proxy it is the
    website's own origin, which must be listed in CORS_ORIGINS. Requests without an
    Origin (not from a browser) are left to the CSRF token check."""

    def __init__(self, app, trusted_origins: list[str]) -> None:
        super().__init__(app)
        self.trusted = frozenset(trusted_origins)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        if request.method in UNSAFE_METHODS and origin is not None and origin not in self.trusted:
            return error_response(403, "csrf_failed", "Request from an unexpected origin.")
        return await call_next(request)
