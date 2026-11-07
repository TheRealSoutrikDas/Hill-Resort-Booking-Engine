"""One succeeded payment per hold, instead of one captured payment.

Migration 0001 allowed at most one payment per hold in succeeded, refund_pending or
refunded. A-50 then said a second payment for an already-paid hold (another browser
tab) was captured and must be refunded, which that index refused to record. The rule
now covers only the payment that paid for the booking (status succeeded); one booking
per hold is still guaranteed by the unique bookings.hold_id and bookings.payment_id.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_payments_one_captured_per_hold", table_name="payments")
    op.create_index(
        "uq_payments_one_succeeded_per_hold",
        "payments",
        ["hold_id"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
    )


def downgrade() -> None:
    # Fails if a hold now has a succeeded payment and a refunded extra one, which the
    # old rule cannot represent; that is the point of this migration.
    op.drop_index("uq_payments_one_succeeded_per_hold", table_name="payments")
    op.create_index(
        "uq_payments_one_captured_per_hold",
        "payments",
        ["hold_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('succeeded', 'refund_pending', 'refunded')"),
    )
