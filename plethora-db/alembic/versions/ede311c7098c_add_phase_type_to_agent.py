"""add_phase_type_to_agent

Revision ID: ede311c7098c
Revises: fa54b90e21f9
Create Date: 2026-07-13 23:32:33.587886

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ede311c7098c'
down_revision: Union[str, Sequence[str], None] = 'fa54b90e21f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    phasetype = sa.Enum('INGESTION', 'EXECUTION', name='phasetype')
    phasetype.create(op.get_bind())
    op.add_column('pipeline_phases', sa.Column('phase_type', phasetype, nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pipeline_phases', 'phase_type')
    sa.Enum(name='phasetype').drop(op.get_bind())
