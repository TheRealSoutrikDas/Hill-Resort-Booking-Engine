"""GM alerts (brief: complaints alert the GM, whatever the model says; A-129).

Every staff role can see the list; only the GM can acknowledge an alert.
"""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DbSession, Now
from app.api.errors import ErrorResponse
from app.api.security import GmUser, StaffUser
from app.db.models import Enquiry, GmAlert, User
from app.services.enquiry_actions import acknowledge_alert

router = APIRouter(prefix="/api/alerts", tags=["enquiries"])

ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}
MAX_LIST = 200


class AlertItem(BaseModel):
    id: int
    reference: str
    lane: str | None
    reason: str
    created_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None


class AlertList(BaseModel):
    open: int
    items: list[AlertItem]


def _items(db, stmt) -> list[AlertItem]:
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.role == "staff"))}
    return [
        AlertItem(
            id=alert.id,
            reference=reference,
            lane=lane,
            reason=alert.reason,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=names.get(alert.acknowledged_by),
        )
        for alert, reference, lane in db.execute(stmt)
    ]


def _query():
    return select(GmAlert, Enquiry.reference, Enquiry.lane).join(
        Enquiry, Enquiry.id == GmAlert.enquiry_id
    )


@router.get("", response_model=AlertList, responses=ERRORS)
def list_alerts(user: StaffUser, db: DbSession, open_only: bool = False) -> AlertList:
    """Open alerts first, then newest first. `open_only=true` hides acknowledged ones."""
    stmt = (
        _query()
        .order_by(
            GmAlert.acknowledged_at.is_not(None), GmAlert.created_at.desc(), GmAlert.id.desc()
        )
        .limit(MAX_LIST)
    )
    if open_only:
        stmt = stmt.where(GmAlert.acknowledged_at.is_(None))
    open_count = db.scalar(
        select(func.count()).select_from(GmAlert).where(GmAlert.acknowledged_at.is_(None))
    )
    return AlertList(open=open_count, items=_items(db, stmt))


@router.post("/{alert_id}/ack", response_model=AlertItem, responses=ERRORS)
def acknowledge(alert_id: int, user: GmUser, db: DbSession, now: Now) -> AlertItem:
    """The GM marks an alert as seen. It cannot be acknowledged twice."""
    alert = acknowledge_alert(db, alert_id, actor=user, now=now)
    [item] = _items(db, _query().where(GmAlert.id == alert.id))
    return item
