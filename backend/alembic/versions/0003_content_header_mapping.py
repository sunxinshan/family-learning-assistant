"""add content header mapping metadata

Revision ID: 0003_content_header_mapping
Revises: 0002_agent_execution_details
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_content_header_mapping"
down_revision: str | None = "0002_agent_execution_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("content_extractions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mapping_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "mapping_source",
                sa.String(length=20),
                nullable=False,
                server_default="rules",
            )
        )
    op.execute("UPDATE content_extractions SET mapping_json = '{}' WHERE mapping_json IS NULL")
    with op.batch_alter_table("content_extractions", schema=None) as batch_op:
        batch_op.alter_column("mapping_json", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("content_extractions", schema=None) as batch_op:
        batch_op.drop_column("mapping_source")
        batch_op.drop_column("mapping_json")
