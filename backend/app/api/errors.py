"""One error format for every failure (A-64, D-32):

    {"error": {"code": "...", "message": "...", "details": ...}, "request_id": "..."}

Domain errors map to fixed HTTP statuses below. Validation errors keep FastAPI's field
locations but never echo the submitted values back. Unexpected errors become a generic
500 in the request middleware (app/main.py), so their details only reach the log.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var
from app.services.enquiry_inbox import EnquiryNotFound, ReclassifyNotAllowed
from app.services.errors import (
    AllotmentTooLow,
    BlackoutBlocked,
    BookingNotFound,
    CancellationNotAllowed,
    CsrfFailed,
    DomainError,
    EmailTaken,
    Forbidden,
    HoldNotActive,
    HoldNotFound,
    InvalidAdminChange,
    InvalidBookingRequest,
    InvalidCredentials,
    InvalidEnquiry,
    InvalidPromoCode,
    InvalidSignup,
    InvalidStay,
    NotAuthenticated,
    NotAvailable,
    PaymentMismatch,
    PaymentNotAllowed,
    PromoCapTooLow,
    PromoCodeTaken,
    PromoNotFound,
    RateLimited,
    RoomTypeNotFound,
    StockLocked,
)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    """Documented in OpenAPI so the generated client knows the error shape."""

    error: ErrorBody
    request_id: str | None = None


# Domain error -> (HTTP status, code used when the error carries no code of its own).
STATUS_FOR: dict[type[DomainError], tuple[int, str]] = {
    InvalidStay: (422, "invalid_stay"),
    InvalidBookingRequest: (422, "invalid_booking_request"),
    InvalidPromoCode: (422, "invalid_promo_code"),
    NotAvailable: (409, "not_available"),
    HoldNotActive: (409, "hold_not_active"),
    CancellationNotAllowed: (409, "cancellation_not_allowed"),
    PaymentNotAllowed: (409, "payment_not_allowed"),
    PaymentMismatch: (409, "payment_mismatch"),
    HoldNotFound: (404, "hold_not_found"),
    BookingNotFound: (404, "booking_not_found"),
    StockLocked: (503, "busy_try_again"),
    NotAuthenticated: (401, "not_authenticated"),
    InvalidCredentials: (401, "invalid_credentials"),
    Forbidden: (403, "forbidden"),
    CsrfFailed: (403, "csrf_failed"),
    EmailTaken: (409, "email_taken"),
    InvalidSignup: (422, "invalid_signup"),
    RateLimited: (429, "rate_limited"),
    RoomTypeNotFound: (404, "room_type_not_found"),
    InvalidAdminChange: (422, "invalid_admin_change"),
    AllotmentTooLow: (409, "allotment_below_commitments"),
    BlackoutBlocked: (409, "active_holds"),
    PromoNotFound: (404, "promo_not_found"),
    PromoCodeTaken: (409, "promo_code_taken"),
    PromoCapTooLow: (409, "cap_below_uses"),
    InvalidEnquiry: (422, "invalid_enquiry"),
    EnquiryNotFound: (404, "enquiry_not_found"),
    ReclassifyNotAllowed: (409, "already_handled"),
}

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 403: "forbidden"}


def error_response(
    status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details),
        request_id=request_id_var.get(),
    )
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def _status_and_code(exc: DomainError) -> tuple[int, str]:
    for cls in type(exc).__mro__:
        if cls in STATUS_FOR:
            status, default_code = STATUS_FOR[cls]
            return status, getattr(exc, "code", None) or default_code
    return 400, "bad_request"  # a DomainError subclass nobody mapped yet


def _details(exc: DomainError) -> Any:
    if isinstance(exc, NotAvailable):
        return {
            "shortfalls": [
                {
                    "room_type_id": s.room_type_id,
                    "date": s.stay_date.isoformat(),
                    "requested": s.requested,
                    "available": s.available,
                }
                for s in exc.shortfalls
            ]
        }
    if isinstance(exc, AllotmentTooLow | BlackoutBlocked):
        return {"nights": exc.nights}
    if isinstance(exc, PromoCapTooLow):
        return {"used": exc.used, "reserved": exc.reserved, "minimum": exc.used + exc.reserved}
    return None


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    status, code = _status_and_code(exc)
    headers = None
    if isinstance(exc, StockLocked):
        headers = {"Retry-After": "1"}
    elif isinstance(exc, RateLimited):
        headers = {"Retry-After": str(exc.retry_after)}
    return error_response(status, code, str(exc), _details(exc), headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Field locations and reasons only; the submitted values ("input") are not echoed,
    # since they can be personal data.
    problems = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return error_response(422, "validation_error", "Some fields are missing or invalid.", problems)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return error_response(
        exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
