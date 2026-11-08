"""add ai_mode to chat_message (respuesta de mentoria vs edicion)

Revision ID: c4e8a7d5b1f2
Revises: b7d3f1a2c9e4
Create Date: 2026-11-08 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a7d5b1f2'
down_revision: Union[str, Sequence[str], None] = 'b7d3f1a2c9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_message', sa.Column('ai_mode', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_message', 'ai_mode')
