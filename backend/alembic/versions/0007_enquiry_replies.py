"""Simulated replies to enquiries.

Adds the reply staff sent (text, time, sender) and the status "replied" (A-127). Real
email and WhatsApp are simulated (brief), so nothing is delivered; the reply is kept for
the record and for the time-to-reply metric (A-128).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'pending', 'classified', 'failed'"
NEW_STATUSES = "'pending', 'classified', 'failed', 'replied'"
REPLY_COMPLETE = (
    "(reply_text IS NULL) = (replied_at IS NULL)"
    " AND (replied_at IS NULL) = (replied_by IS NULL)"
    " AND (status = 'replied') = (replied_at IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column("enquiries", sa.Column("reply_text", sa.Text(), nullable=True))
    op.add_column("enquiries", sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("enquiries", sa.Column("replied_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_enquiries_replied_by_users"), "enquiries", "users", ["replied_by"], ["id"]
    )
    op.drop_constraint(op.f("ck_enquiries_status_valid"), "enquiries", type_="check")
    op.create_check_constraint("status_valid", "enquiries", f"status IN ({NEW_STATUSES})")
    op.create_check_constraint("reply_complete", "enquiries", REPLY_COMPLETE)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_enquiries_reply_complete"), "enquiries", type_="check")
    op.execute("UPDATE enquiries SET status = 'classified' WHERE status = 'replied'")
    op.drop_constraint(op.f("ck_enquiries_status_valid"), "enquiries", type_="check")
    op.create_check_constraint("status_valid", "enquiries", f"status IN ({OLD_STATUSES})")
    op.drop_constraint(op.f("fk_enquiries_replied_by_users"), "enquiries", type_="foreignkey")
    op.drop_column("enquiries", "replied_by")
    op.drop_column("enquiries", "replied_at")
    op.drop_column("enquiries", "reply_text")
