"""add_approved_halted_to_session_status

Revision ID: 861a3f171156
Revises: ac7c75b20ba7
Create Date: 2026-09-02 01:19:43.634749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '861a3f171156'
down_revision: Union[str, Sequence[str], None] = 'ac7c75b20ba7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'approved'")
    op.execute("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'halted'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; no-op on downgrade
    pass
