"""add agent execution detail fields

Revision ID: 0002_agent_execution_details
Revises: d84e7517a216
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_agent_execution_details"
down_revision: str | None = "d84e7517a216"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("token_usage_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("error_message", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_column("error_message")
        batch_op.drop_column("token_usage_json")
