"""add ai provider config to diagram (CU-17: proveedor de IA local/nube)

Revision ID: e5a9c1d4f8b3
Revises: d2f6b8c3a7e1
Create Date: 2026-11-08 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a9c1d4f8b3'
down_revision: Union[str, Sequence[str], None] = 'd2f6b8c3a7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('diagram', sa.Column('ai_provider', sa.String(length=32), nullable=True))
    op.add_column('diagram', sa.Column('ai_base_url', sa.String(length=500), nullable=True))
    op.add_column('diagram', sa.Column('ai_model', sa.String(length=200), nullable=True))
    op.add_column('diagram', sa.Column('ai_api_key', sa.String(length=500), nullable=True))
    op.add_column('chat_message', sa.Column('ai_model_label', sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_message', 'ai_model_label')
    op.drop_column('diagram', 'ai_api_key')
    op.drop_column('diagram', 'ai_model')
    op.drop_column('diagram', 'ai_base_url')
    op.drop_column('diagram', 'ai_provider')
