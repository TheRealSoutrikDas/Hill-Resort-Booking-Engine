"""AI evaluation on real enquiries.

`ai_eval` keeps what the AI decided (written only by the pipeline); `actual_eval` keeps
what the GM approved as right, with who and when (A-145). Comparing the two measures
AI accuracy on real enquiries. Enquiries classified before this migration have no
`ai_eval` and are left out of that measure rather than guessed.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERIFIED_COMPLETE = (
    "(actual_eval IS NULL) = (verified_at IS NULL)"
    " AND (verified_at IS NULL) = (verified_by IS NULL)"
)


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.add_column("enquiries", sa.Column("ai_eval", jsonb, nullable=True))
    op.add_column("enquiries", sa.Column("actual_eval", jsonb, nullable=True))
    op.add_column("enquiries", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("enquiries", sa.Column("verified_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_enquiries_verified_by_users"), "enquiries", "users", ["verified_by"], ["id"]
    )
    op.create_check_constraint("verified_complete", "enquiries", VERIFIED_COMPLETE)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_enquiries_verified_complete"), "enquiries", type_="check")
    op.drop_constraint(op.f("fk_enquiries_verified_by_users"), "enquiries", type_="foreignkey")
    for column in ("verified_by", "verified_at", "actual_eval", "ai_eval"):
        op.drop_column("enquiries", column)
