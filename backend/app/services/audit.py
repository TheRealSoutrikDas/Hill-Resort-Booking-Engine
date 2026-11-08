"""Audit trail: who changed what, when, from which value to which (A-106).

Used for admin changes now and for enquiry corrections in stage 5 (brief).
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def record(
    session: Session,
    *,
    actor_id: int,
    entity_type: str,
    entity_id: str,
    action: str,
    now: datetime,
    field: str | None = None,
    old: Any = None,
    new: Any = None,
) -> AuditLog:
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        field=field,
        old_value=old,
        new_value=new,
        actor_user_id=actor_id,
        created_at=now,
    )
    session.add(entry)
    session.flush()
    return entry
