"""The three-step booking flow for a signed-in guest (brief screen 3, A-43).

Step 1 `POST /api/holds`, step 2 `PUT /api/holds/{id}/guest`, step 3
`POST /api/holds/{id}/payment`. Another guest's hold is "not found" (404).
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Clock, DbSession, Now, Provider, Rules, SessionFactory
from app.api.errors import ErrorResponse
from app.api.schemas import PriceOut, StayIn, stored_price_out, to_request
from app.api.security import GuestUser
from app.db.models import Booking, Hold, PromoCode, User
from app.db.models.enums import HoldStatus
from app.services.checkout import pay_for_hold
from app.services.holds import create_hold, get_owned_hold, release_hold, set_guest_details

router = APIRouter(prefix="/api/holds", tags=["booking"])

ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


class GuestDetails(BaseModel):
    name: str
    email: str
    phone: str


class GuestSuggestion(BaseModel):
    """The account's own details, to prefill booking step 2 (A-98). Editable."""

    name: str
    email: str
    phone: str | None  # optional at sign-up


class HoldOut(BaseModel):
    id: UUID
    status: Literal["active", "expired", "released", "converted"]
    expires_at: datetime
    check_in: date
    check_out: date
    price: PriceOut
    guest: GuestDetails | None
    # Until guest details are saved: the account's details to prefill the form.
    guest_suggestion: GuestSuggestion | None
    booking_reference: str | None  # once paid


class GuestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    email: str = Field(max_length=320)
    phone: str = Field(max_length=40)


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Test mode only: the outcome the mock gateway should simulate (A-59).
    simulate: Literal["success", "decline", "timeout"] = "success"


class PaymentOut(BaseModel):
    """Always returned with 200 once the gateway was called (A-87): read `status`."""

    status: Literal[
        "confirmed", "declined", "timed_out", "processing", "refunded", "refund_pending"
    ]
    booking_reference: str | None = None
    failure: str | None = None  # why a captured payment was refunded


def hold_out(db: Session, hold: Hold, now: datetime) -> HoldOut:
    status = hold.status
    if status == HoldStatus.ACTIVE and hold.expires_at <= now:
        status = "expired"
    promo = db.get(PromoCode, hold.promo_code_id) if hold.promo_code_id else None
    reference = db.scalar(select(Booking.reference).where(Booking.hold_id == hold.id))
    guest, suggestion = None, None
    if hold.guest_name and hold.guest_email and hold.guest_phone:
        guest = GuestDetails(name=hold.guest_name, email=hold.guest_email, phone=hold.guest_phone)
    else:
        account = db.get(User, hold.user_id)
        suggestion = GuestSuggestion(
            name=account.full_name, email=account.email, phone=account.phone
        )
    return HoldOut(
        id=hold.id,
        status=status,
        expires_at=hold.expires_at,
        check_in=hold.check_in,
        check_out=hold.check_out,
        price=stored_price_out(db, hold.items, promo),
        guest=guest,
        guest_suggestion=suggestion,
        booking_reference=reference,
    )


@router.post("", status_code=201, response_model=HoldOut, responses=ERRORS)
def start_booking(body: StayIn, user: GuestUser, db: DbSession, now: Now, rules: Rules) -> HoldOut:
    """Step 1: hold the rooms for 10 minutes at the quoted price."""
    result = create_hold(
        db, user.id, to_request(db, body), now=now, rules=rules, promo_code=body.promo_code
    )
    return hold_out(db, get_owned_hold(db, user.id, result.hold_id), now)


@router.get("/{hold_id}", response_model=HoldOut, responses=ERRORS)
def get_hold(hold_id: UUID, user: GuestUser, db: DbSession, now: Now) -> HoldOut:
    """The hold, so checkout survives a page reload."""
    return hold_out(db, get_owned_hold(db, user.id, hold_id), now)


@router.put("/{hold_id}/guest", response_model=HoldOut, responses=ERRORS)
def set_guest(hold_id: UUID, body: GuestIn, user: GuestUser, db: DbSession, now: Now) -> HoldOut:
    """Step 2: who is staying (prefilled from the account in the frontend; editable)."""
    hold = set_guest_details(
        db, user.id, hold_id, name=body.name, email=body.email, phone=body.phone, now=now
    )
    return hold_out(db, hold, now)


@router.delete("/{hold_id}", status_code=204, responses=ERRORS)
def release(hold_id: UUID, user: GuestUser, db: DbSession) -> None:
    """Back or change rooms: give the stock back now (A-44)."""
    release_hold(db, user.id, hold_id)


@router.post("/{hold_id}/payment", response_model=PaymentOut, responses=ERRORS)
def pay(
    hold_id: UUID,
    body: PaymentIn,
    user: GuestUser,
    factory: SessionFactory,
    provider: Provider,
    rules: Rules,
    clock: Clock,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=64)],
) -> PaymentOut:
    """Step 3: pay. The same Idempotency-Key never charges twice (A-61).

    Checkout runs its own short transactions and calls the gateway outside them (D-31).
    The sign-in check's read-only transaction stays open meanwhile but holds no row
    locks, so nothing waits on it (D-36)."""
    result = pay_for_hold(
        factory,
        provider,
        user.id,
        hold_id,
        idempotency_key,
        rules=rules,
        simulate=body.simulate,
        clock=clock,
    )
    return PaymentOut(
        status=result.status, booking_reference=result.booking_reference, failure=result.failure
    )
