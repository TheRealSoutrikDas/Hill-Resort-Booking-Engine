"""Require an account for holds and bookings.

Signing in is now required to book (A-43, D-24), so holds.user_id and bookings.user_id
become NOT NULL. The database then refuses any hold or booking without an account,
even if service code had a bug.

Existing rows without an account cannot be given one automatically, so the upgrade
stops with instructions instead of guessing. On a development database the fix is to
rebuild it; a production database would need an agreed backfill plan first.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("holds", "bookings")


def upgrade() -> None:
    conn = op.get_bind()
    without_account = {
        table: conn.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE user_id IS NULL")
        ).scalar_one()
        for table in _TABLES
    }
    if any(without_account.values()):
        counts = ", ".join(f"{n} {table}" for table, n in without_account.items() if n)
        raise RuntimeError(
            f"Cannot require accounts: {counts} have no user_id. "
            "On a development database, rebuild it: "
            "`alembic downgrade base && alembic upgrade head && python -m app.seed --reset`."
        )
    for table in _TABLES:
        op.alter_column(table, "user_id", existing_type=sa.BigInteger(), nullable=False)


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "user_id", existing_type=sa.BigInteger(), nullable=True)
