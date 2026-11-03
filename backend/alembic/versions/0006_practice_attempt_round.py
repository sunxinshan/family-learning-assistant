"""add practice attempt round number

Revision ID: 0006_practice_attempt_round
Revises: 0005_practice_attempt_sequence
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_practice_attempt_round"
down_revision: str | None = "0005_practice_attempt_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("practice_attempts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "round_no",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("practice_attempts", schema=None) as batch_op:
        batch_op.drop_column("round_no")
