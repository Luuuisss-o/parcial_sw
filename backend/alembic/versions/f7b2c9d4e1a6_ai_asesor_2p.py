"""Segundo parcial: asesor IA configurable, estado de consultas y propuestas.

- diagram.ai_enabled: el dueño puede desactivar al asesor del diagrama.
- diagram.ai_proposals_enabled: el asesor puede (o no) proponer cambios.
- chat_message.ai_status: estado de cada consulta a la IA
  (pending/running/completed/failed), persistido.
- ai_proposal: cambios que propone el asesor; nadie los aplica hasta que un
  integrante autorizado los acepta.

Revision ID: f7b2c9d4e1a6
Revises: e5a9c1d4f8b3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7b2c9d4e1a6"
down_revision: Union[str, Sequence[str], None] = "e5a9c1d4f8b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diagram", sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("diagram", sa.Column("ai_proposals_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("chat_message", sa.Column("ai_status", sa.String(16), nullable=True))
    op.create_table(
        "ai_proposal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("diagram_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_message.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by_name", sa.String(120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("operations", postgresql.JSONB(), nullable=False),
        sa.Column("base_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_by_name", sa.String(120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_proposal")
    op.drop_column("chat_message", "ai_status")
    op.drop_column("diagram", "ai_proposals_enabled")
    op.drop_column("diagram", "ai_enabled")
