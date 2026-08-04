"""mark the Alembic-only bootstrap compatibility boundary

Revision ID: 20260713_0012
Revises: 20260713_0011
Create Date: 2026-07-14 12:15:00
"""

from __future__ import annotations


revision = '20260713_0012'
down_revision = '20260713_0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Metadata-only compatibility boundary for the runtime cutover."""


def downgrade() -> None:
    """Metadata-only rollback to code that still understands this revision."""
