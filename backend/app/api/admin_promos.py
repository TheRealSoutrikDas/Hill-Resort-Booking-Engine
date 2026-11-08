"""Admin promo codes (brief screen 6, A-105 to A-107). Reservations team and the GM."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.admin import ERRORS, AdminUser
from app.api.deps import DbSession, Now, Rules
from app.api.errors import ErrorResponse
from app.services import admin_promos as service
from app.services.dates import business_today
from app.services.errors import InvalidAdminChange

router = APIRouter(prefix="/api/admin/promos", tags=["admin"])


class PromoOut(BaseModel):
    code: str
    percent_off: int
    valid_from: date
    valid_to: date
    max_uses: int | None
    used: int
    reserved: int
    uses_left: int | None
    is_active: bool
    usable_today: bool


class PromoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=64)
    percent_off: int
    valid_from: date
    valid_to: date
    max_uses: int | None = None


class PromoUpdate(BaseModel):
    # extra="forbid": code and percent cannot be changed once created (A-105).
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    valid_to: date | None = None
    max_uses: int | None = Field(default=None, description="Send null to remove the cap")


ROUTE_ERRORS = {**ERRORS, 404: {"model": ErrorResponse}}


@router.get("", response_model=list[PromoOut], responses=ROUTE_ERRORS)
def list_promos(user: AdminUser, db: DbSession, now: Now, rules: Rules) -> list[PromoOut]:
    """Every code with its uses, uses reserved by holds, and whether it works today."""
    views = service.list_promos(db, today=business_today(now, rules.tz), now=now)
    return [PromoOut(**v.__dict__) for v in views]


@router.post("", status_code=201, response_model=PromoOut, responses=ROUTE_ERRORS)
def create_promo(
    body: PromoCreate, user: AdminUser, db: DbSession, now: Now, rules: Rules
) -> PromoOut:
    view = service.create_promo(
        db,
        actor_id=user.id,
        code=body.code,
        percent_off=body.percent_off,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        max_uses=body.max_uses,
        today=business_today(now, rules.tz),
        now=now,
    )
    return PromoOut(**view.__dict__)


@router.patch("/{code}", response_model=PromoOut, responses=ROUTE_ERRORS)
def update_promo(
    code: str, body: PromoUpdate, user: AdminUser, db: DbSession, now: Now, rules: Rules
) -> PromoOut:
    """Switch on or off, move the end date, or change the cap. Only fields sent change."""
    sent = body.model_fields_set
    changes = {}
    if "is_active" in sent:
        if body.is_active is None:
            raise InvalidAdminChange("invalid_switch", "is_active must be true or false.")
        changes["is_active"] = body.is_active
    if "valid_to" in sent:
        if body.valid_to is None:
            raise InvalidAdminChange("invalid_end_date", "valid_to needs a date.")
        changes["valid_to"] = body.valid_to
    if "max_uses" in sent:
        changes["max_uses"] = body.max_uses
    view = service.update_promo(
        db,
        actor_id=user.id,
        code=code,
        lock_timeout_ms=rules.lock_timeout_ms,
        today=business_today(now, rules.tz),
        now=now,
        **changes,
    )
    return PromoOut(**view.__dict__)
