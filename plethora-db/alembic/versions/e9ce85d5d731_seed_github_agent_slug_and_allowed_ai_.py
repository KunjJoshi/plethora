"""Seed github agent slug and allowed ai models

Revision ID: e9ce85d5d731
Revises: ede311c7098c
Create Date: 2026-07-13 23:36:20.200861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9ce85d5d731'
down_revision: Union[str, Sequence[str], None] = 'ede311c7098c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            "INSERT INTO agent_slugs (slug_name, agent_type) "
            "VALUES ('github', 'Coding Agent') RETURNING id"
        )
    )
    agent_slug_id = result.scalar()

    conn.execute(
        sa.text(
            "INSERT INTO allowed_ai_models (agent_slug_id, ai_name) VALUES "
            "(:slug_id, 'claude_code'), (:slug_id, 'openai_codex')"
        ),
        {"slug_id": str(agent_slug_id)},
    )


def downgrade() -> None:
    # CASCADE on allowed_ai_models cleans up the AI rows automatically
    op.get_bind().execute(
        sa.text("DELETE FROM agent_slugs WHERE slug_name = 'github'")
    )
