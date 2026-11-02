"""add practice attempt sequence

Revision ID: 0005_practice_attempt_sequence
Revises: 0004_practice_wrong_review
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_practice_attempt_sequence"
down_revision: str | None = "0004_practice_wrong_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("practice_attempts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "attempt_no",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("practice_attempts", schema=None) as batch_op:
        batch_op.drop_column("attempt_no")
