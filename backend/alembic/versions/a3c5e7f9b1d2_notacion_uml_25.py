"""Notación UML 2.5 completa para diagramas de clases.

- clase.tipo_clase: class | abstract | interface | enumeration
  («interface», «enumeration», nombre en cursiva para abstractas).
- atributo: visibilidad (+ - # ~), estático (subrayado), derivado (/),
  multiplicidad ([0..*]) y valor inicial (= valor).
- metodo: visibilidad, estático, abstracto (cursiva) y parámetros
  ("nombre: Tipo, ...").
- relacion: tipo REALIZATION (interfaz implementada: línea punteada con
  triángulo hueco), nombres de rol y navegabilidad en cada extremo.

Todo es aditivo y con valores por defecto: los diagramas existentes se ven
igual salvo por la visibilidad, que UML muestra siempre (- atributos,
+ métodos, la convención habitual).

Revision ID: a3c5e7f9b1d2
Revises: f7b2c9d4e1a6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d2"
down_revision: Union[str, Sequence[str], None] = "f7b2c9d4e1a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE no puede ir dentro de una transacción en
    # versiones viejas de Postgres: se ejecuta en un bloque autocommit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE reltype ADD VALUE IF NOT EXISTS 'REALIZATION'")

    op.add_column("clase", sa.Column("tipo_clase", sa.String(20), nullable=False, server_default="class"))

    op.add_column("atributo", sa.Column("visibilidad", sa.String(1), nullable=False, server_default="-"))
    op.add_column("atributo", sa.Column("es_estatico", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("atributo", sa.Column("es_derivado", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("atributo", sa.Column("multiplicidad", sa.String(20), nullable=True))
    op.add_column("atributo", sa.Column("valor_inicial", sa.String(120), nullable=True))

    op.add_column("metodo", sa.Column("visibilidad", sa.String(1), nullable=False, server_default="+"))
    op.add_column("metodo", sa.Column("es_estatico", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("metodo", sa.Column("es_abstracto", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("metodo", sa.Column("parametros", sa.String(300), nullable=False, server_default=""))

    op.add_column("relacion", sa.Column("rol_origen", sa.String(80), nullable=True))
    op.add_column("relacion", sa.Column("rol_destino", sa.String(80), nullable=True))
    op.add_column("relacion", sa.Column("navegable_origen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("relacion", sa.Column("navegable_destino", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for col in ("navegable_destino", "navegable_origen", "rol_destino", "rol_origen"):
        op.drop_column("relacion", col)
    for col in ("parametros", "es_abstracto", "es_estatico", "visibilidad"):
        op.drop_column("metodo", col)
    for col in ("valor_inicial", "multiplicidad", "es_derivado", "es_estatico", "visibilidad"):
        op.drop_column("atributo", col)
    op.drop_column("clase", "tipo_clase")
    # Postgres no permite quitar un valor de un enum: las realizaciones se
    # convierten en dependencias para no dejar filas inválidas.
    op.execute("UPDATE relacion SET tipo = 'DEPENDENCY' WHERE tipo = 'REALIZATION'")
