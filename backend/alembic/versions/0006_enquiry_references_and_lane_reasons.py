"""Enquiry reference sequence and lane reasons.

New enquiries get references ENQ-5001, ENQ-5002, ... from a database sequence, so two
submissions at once can never clash (A-120). `lane_reasons` records why the pipeline
chose a lane, for example ["low_confidence"] for Unsorted (D-42). Written by hand:
Alembic autogenerate does not detect sequences.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE enquiry_reference_seq START WITH 5001")
    op.add_column(
        "enquiries",
        sa.Column(
            "lane_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("enquiries", "lane_reasons")
    op.execute("DROP SEQUENCE enquiry_reference_seq")
