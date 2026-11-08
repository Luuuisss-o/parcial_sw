"""add chat_message (chat grupal del diagrama + consultas a la IA)

Revision ID: b7d3f1a2c9e4
Revises: 8a1c2e4f6b90
Create Date: 2026-11-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7d3f1a2c9e4'
down_revision: Union[str, Sequence[str], None] = '8a1c2e4f6b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chat_message',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('diagram_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('diagram.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Enum('USER', 'ASSISTANT', 'ERROR', name='chat_role'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('author_name', sa.String(length=120), nullable=False),
        sa.Column('author_email', sa.String(length=160), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('asks_ai', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('reply_to_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('chat_message.id', ondelete='SET NULL'), nullable=True),
        sa.Column('addressed_to_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('addressed_to_name', sa.String(length=120), nullable=True),
        sa.Column('actions', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('seq', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.UniqueConstraint('seq', name='uq_chat_message_seq'),
    )
    op.create_index('ix_chat_message_diagram_id', 'chat_message', ['diagram_id'])
    op.create_index('ix_chat_message_author_id', 'chat_message', ['author_id'])
    op.create_index('ix_chat_message_created_at', 'chat_message', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_chat_message_created_at', table_name='chat_message')
    op.drop_index('ix_chat_message_author_id', table_name='chat_message')
    op.drop_index('ix_chat_message_diagram_id', table_name='chat_message')
    op.drop_table('chat_message')
    sa.Enum(name='chat_role').drop(op.get_bind(), checkfirst=True)
