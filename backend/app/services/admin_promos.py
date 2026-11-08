"""Admin promo codes: list, create, and change the switch, end date or cap
(brief screen 6, A-105 to A-107, D-40).

A promo's code and percent never change once created, so reports and past bookings
stay clear; to change a discount, switch the code off and create a new one. Lowering
the cap locks the promo row, the same lock a hold takes to reserve a use (D-30), so a
guest cannot reserve a use between the check and the change.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import PromoCode
from app.services import audit
from app.services.errors import InvalidAdminChange, PromoCapTooLow, PromoCodeTaken, PromoNotFound
from app.services.promos import held_uses, lock_promo, normalize_promo_code

CODE_RE = re.compile(r"^[A-Z0-9]{3,32}$")
MAX_PERCENT_OFF = 90  # a 100% code would make a zero-amount payment (A-107)

UNCHANGED: Any = object()  # "this field was not sent" in update_promo


@dataclass(frozen=True)
class PromoView:
    code: str
    percent_off: int
    valid_from: date
    valid_to: date
    max_uses: int | None
    used: int
    reserved: int  # by active holds
    uses_left: int | None  # None: no cap
    is_active: bool
    usable_today: bool


def _view(session: Session, promo: PromoCode, today: date, now: datetime) -> PromoView:
    reserved = held_uses(session, promo.id, now)
    left = None if promo.max_uses is None else max(promo.max_uses - promo.used_count - reserved, 0)
    return PromoView(
        code=promo.code,
        percent_off=promo.percent_off,
        valid_from=promo.valid_from,
        valid_to=promo.valid_to,
        max_uses=promo.max_uses,
        used=promo.used_count,
        reserved=reserved,
        uses_left=left,
        is_active=promo.is_active,
        usable_today=promo.is_active
        and promo.valid_from <= today <= promo.valid_to
        and (left is None or left > 0),
    )


def _snapshot(promo: PromoCode) -> dict[str, Any]:
    return {
        "is_active": promo.is_active,
        "valid_to": promo.valid_to.isoformat(),
        "max_uses": promo.max_uses,
    }


def list_promos(session: Session, *, today: date, now: datetime) -> list[PromoView]:
    promos = session.scalars(select(PromoCode).order_by(PromoCode.valid_to.desc(), PromoCode.code))
    return [_view(session, p, today, now) for p in promos]


def create_promo(
    session: Session,
    *,
    actor_id: int,
    code: str,
    percent_off: int,
    valid_from: date,
    valid_to: date,
    max_uses: int | None,
    today: date,
    now: datetime,
) -> PromoView:
    code = normalize_promo_code(code)
    if not CODE_RE.fullmatch(code):
        raise InvalidAdminChange("invalid_code", "Use 3 to 32 letters and digits.")
    if not 1 <= percent_off <= MAX_PERCENT_OFF:
        raise InvalidAdminChange(
            "invalid_percent", f"The discount must be 1 to {MAX_PERCENT_OFF}%."
        )
    if valid_to < valid_from:
        raise InvalidAdminChange("range_reversed", "The end date is before the start date.")
    if valid_to < today:
        raise InvalidAdminChange("date_in_past", "The code would already have expired.")
    if max_uses is not None and max_uses < 1:
        raise InvalidAdminChange("invalid_cap", "The cap must be at least 1, or empty for no cap.")

    promo = PromoCode(
        code=code,
        percent_off=percent_off,
        valid_from=valid_from,
        valid_to=valid_to,
        max_uses=max_uses,
        created_at=now,
    )
    try:
        with session.begin_nested():
            session.add(promo)
            session.flush()
    except IntegrityError as exc:
        if (
            getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            == "uq_promo_codes_code"
        ):
            raise PromoCodeTaken(f"{code} already exists.") from exc
        raise
    audit.record(
        session,
        actor_id=actor_id,
        entity_type="promo_code",
        entity_id=code,
        action="create_promo",
        new={
            "percent_off": percent_off,
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
            "max_uses": max_uses,
        },
        now=now,
    )
    return _view(session, promo, today, now)


def update_promo(
    session: Session,
    *,
    actor_id: int,
    code: str,
    is_active: bool = UNCHANGED,
    valid_to: date = UNCHANGED,
    max_uses: int | None = UNCHANGED,
    lock_timeout_ms: int,
    today: date,
    now: datetime,
) -> PromoView:
    """Change only the switch, the end date or the cap (A-105). `max_uses=None` removes
    the cap; a field left as UNCHANGED keeps its value."""
    promo_id = session.scalar(
        select(PromoCode.id).where(PromoCode.code == normalize_promo_code(code))
    )
    if promo_id is None:
        raise PromoNotFound("That promo code does not exist.")
    promo = lock_promo(session, promo_id, lock_timeout_ms)
    before = _snapshot(promo)

    if valid_to is not UNCHANGED:
        if valid_to < promo.valid_from:
            raise InvalidAdminChange("range_reversed", "The end date is before the start date.")
        if valid_to < today:
            raise InvalidAdminChange(
                "date_in_past", "Switch the code off instead of ending it in the past."
            )
        promo.valid_to = valid_to
    if max_uses is not UNCHANGED and max_uses is not None:
        if max_uses < 1:
            raise InvalidAdminChange(
                "invalid_cap", "The cap must be at least 1, or empty for no cap."
            )
        reserved = held_uses(session, promo.id, now)
        if max_uses < promo.used_count + reserved:
            raise PromoCapTooLow(promo.used_count, reserved)
    if max_uses is not UNCHANGED:
        promo.max_uses = max_uses
    if is_active is not UNCHANGED:
        promo.is_active = is_active
    session.flush()

    after = _snapshot(promo)
    if after != before:
        audit.record(
            session,
            actor_id=actor_id,
            entity_type="promo_code",
            entity_id=promo.code,
            action="update_promo",
            old={k: v for k, v in before.items() if after[k] != v},
            new={k: v for k, v in after.items() if before[k] != v},
            now=now,
        )
    return _view(session, promo, today, now)
