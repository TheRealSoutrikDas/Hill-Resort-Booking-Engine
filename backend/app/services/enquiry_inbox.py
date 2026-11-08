"""Reading the enquiry inbox, and the re-run rule (A-123, A-125, D-43)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Enquiry
from app.db.models.enums import EnquiryStatus
from app.services.errors import DomainError

AUDIT_ENTITY = "enquiry"
# Staff actions that make a re-run unsafe: it would overwrite the person's work (A-125),
# or the GM's approval (A-145).
STAFF_DECISIONS = ("correct", "reroute", "reply", "verify")


class EnquiryNotFound(DomainError):
    """No enquiry with this reference."""


class ReclassifyNotAllowed(DomainError):
    """A staff member has already corrected, re-routed or replied to this enquiry."""

    code = "already_handled"


def normalize_reference(reference: str) -> str:
    return reference.strip().upper()


def get_enquiry(session: Session, reference: str, *, lock: bool = False) -> Enquiry:
    stmt = select(Enquiry).where(Enquiry.reference == normalize_reference(reference))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    enquiry = session.scalar(stmt)
    if enquiry is None:
        raise EnquiryNotFound("No enquiry with that reference.")
    return enquiry


def staff_decisions(session: Session, enquiry: Enquiry) -> int:
    return session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.entity_type == AUDIT_ENTITY,
            AuditLog.entity_id == enquiry.reference,
            AuditLog.action.in_(STAFF_DECISIONS),
        )
    )


def can_reclassify(session: Session, enquiry: Enquiry) -> bool:
    if enquiry.status in (EnquiryStatus.PENDING, EnquiryStatus.FAILED):
        return True
    return staff_decisions(session, enquiry) == 0


def history(session: Session, enquiry: Enquiry) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == AUDIT_ENTITY, AuditLog.entity_id == enquiry.reference)
            .order_by(AuditLog.created_at, AuditLog.id)
        )
    )
