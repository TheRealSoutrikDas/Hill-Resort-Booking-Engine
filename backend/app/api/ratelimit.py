"""Rate-limit dependencies for routes (A-79 to A-83, D-34).

The client is identified by `request.client.host`. Behind the Next.js proxy, uvicorn
sets it from X-Forwarded-For, but only for requests from a trusted proxy address
(FORWARDED_ALLOW_IPS; this machine by default), so a client cannot fake its IP (A-81).

A refused attempt is logged with the route and the limit's name only: never the IP or
the email (A-83).
"""

import hashlib
import logging
from collections.abc import Callable

from fastapi import Request

from app.core.config import Settings
from app.core.ratelimit import SlidingWindowLimiter
from app.services.errors import RateLimited
from app.services.validation import normalize_email

logger = logging.getLogger("app.ratelimit")

# Limit name -> (setting for the count, setting for the window in seconds).
PER_IP_LIMITS = {
    "login": ("rate_login_per_ip", "rate_login_per_ip_window_s"),
    "signup": ("rate_signup_per_ip", "rate_signup_per_ip_window_s"),
    "lookup": ("rate_lookup_per_ip", "rate_lookup_per_ip_window_s"),
    "enquiry": ("rate_enquiry_per_ip", "rate_enquiry_per_ip_window_s"),
}


def _limiter(request: Request) -> SlidingWindowLimiter:
    return request.app.state.limiter


def _refuse(request: Request, limit_name: str, retry_after: int) -> RateLimited:
    route = request.scope.get("route")
    logger.warning(
        "rate limited",
        extra={"route": route.path if route is not None else "unmatched", "limit": limit_name},
    )
    return RateLimited(retry_after)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit_per_ip(name: str) -> Callable[[Request], None]:
    """A dependency that counts one attempt per call for this client IP."""
    count_field, window_field = PER_IP_LIMITS[name]

    def dependency(request: Request) -> None:
        settings: Settings = request.app.state.settings
        retry_after = _limiter(request).hit(
            f"{name}_ip:{client_ip(request)}",
            getattr(settings, count_field),
            getattr(settings, window_field),
        )
        if retry_after is not None:
            raise _refuse(request, f"{name}_per_ip", retry_after)

    return dependency


class LoginFailures:
    """Failed logins per account email (A-80). The key is a hash of the email, so raw
    addresses are not kept even in memory. A correct login clears the count."""

    def __init__(self, request: Request, email: str) -> None:
        self.request = request
        self.settings: Settings = request.app.state.settings
        digest = hashlib.sha256(normalize_email(email).encode()).hexdigest()
        self.key = f"login_email:{digest}"

    def check(self) -> None:
        retry_after = _limiter(self.request).blocked_for(
            self.key,
            self.settings.rate_login_failures_per_email,
            self.settings.rate_login_failures_window_s,
        )
        if retry_after is not None:
            raise _refuse(self.request, "login_failures_per_email", retry_after)

    def failed(self) -> None:
        _limiter(self.request).record(self.key, self.settings.rate_login_failures_window_s)

    def succeeded(self) -> None:
        _limiter(self.request).clear(self.key)
