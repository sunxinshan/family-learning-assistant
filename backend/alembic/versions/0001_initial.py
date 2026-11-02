"""Initial migration baseline.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-02
"""
from collections.abc import Sequence

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the migration baseline without business tables."""


def downgrade() -> None:
    """Remove the migration baseline."""
