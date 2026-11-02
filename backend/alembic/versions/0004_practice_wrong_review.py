"""add wrong-question practice attempt scope

Revision ID: 0004_practice_wrong_review
Revises: 0003_content_header_mapping
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_practice_wrong_review"
down_revision: str | None = "0003_content_header_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("practice_attempts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="regular")
        )
        batch_op.add_column(sa.Column("target_entry_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("practice_attempts", schema=None) as batch_op:
        batch_op.drop_column("target_entry_ids")
        batch_op.drop_column("kind")
