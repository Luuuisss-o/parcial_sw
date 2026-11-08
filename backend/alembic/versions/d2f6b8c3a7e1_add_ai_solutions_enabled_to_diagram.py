"""add ai_solutions_enabled to diagram (la IA puede entregar soluciones, configurable)

Revision ID: d2f6b8c3a7e1
Revises: c4e8a7d5b1f2
Create Date: 2026-11-08 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f6b8c3a7e1'
down_revision: Union[str, Sequence[str], None] = 'c4e8a7d5b1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'diagram',
        sa.Column('ai_solutions_enabled', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('diagram', 'ai_solutions_enabled')
