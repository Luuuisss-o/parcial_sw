"""add es_clase_asociacion to relacion

Revision ID: 8a1c2e4f6b90
Revises: 3f9f653ec7cc
Create Date: 2026-09-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1c2e4f6b90'
down_revision: Union[str, Sequence[str], None] = '3f9f653ec7cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'relacion',
        sa.Column('es_clase_asociacion', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('relacion', 'es_clase_asociacion')
