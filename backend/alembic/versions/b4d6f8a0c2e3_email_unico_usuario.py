"""Email único por usuario (sin distinguir mayúsculas).

Hasta ahora los usuarios se creaban directo en la base y nada impedía dos
cuentas con el mismo correo. Con el registro público (POST /auth/sign-up)
dos altas simultáneas podrían crearlas: el índice único sobre lower(email)
lo impide a nivel de base, no solo con el chequeo previo del endpoint.

Revision ID: b4d6f8a0c2e3
Revises: a3c5e7f9b1d2
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b4d6f8a0c2e3"
down_revision: Union[str, Sequence[str], None] = "a3c5e7f9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_email_lower ON "user" (lower(email))')


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_email_lower")
