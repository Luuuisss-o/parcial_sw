from sqlalchemy import String, Boolean, ForeignKey, Enum, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base
import enum, uuid
import datetime
from typing import List, Optional
from sqlalchemy import Integer, String

# Tipos de relación UML (puedes ampliar según tu necesidad real)
class RelType(str, enum.Enum):
    ASSOCIATION = "ASSOCIATION"
    AGGREGATION = "AGGREGATION"
    COMPOSITION = "COMPOSITION"
    INHERITANCE = "INHERITANCE"
    DEPENDENCY = "DEPENDENCY"


# =========================
# Diagrama
# =========================
class Diagram(Base):
    __tablename__ = "diagram"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relaciones
    owner: Mapped["User"] = relationship()
    classes: Mapped[List["Clase"]] = relationship(back_populates="diagram", cascade="all, delete-orphan", passive_deletes=True)
    relations: Mapped[List["Relacion"]] = relationship(back_populates="diagram", cascade="all, delete-orphan", passive_deletes=True)
    collaborators: Mapped[List["DiagramCollaborator"]] = relationship(back_populates="diagram", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def owner_email(self) -> str:
        return self.owner.email


# =========================
# Colaborador de un diagrama
# =========================
class CollaboratorRole(str, enum.Enum):
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class DiagramCollaborator(Base):
    __tablename__ = "diagram_collaborator"
    __table_args__ = (
        UniqueConstraint("diagram_id", "user_id", name="uq_diagram_collaborator_diagram_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diagram_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[CollaboratorRole] = mapped_column(Enum(CollaboratorRole, name="collaborator_role"), nullable=False, server_default="EDITOR")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    diagram: Mapped["Diagram"] = relationship(back_populates="collaborators")
    user: Mapped["User"] = relationship()


# =========================
# Clase UML
# =========================
class Clase(Base):
    __tablename__ = "clase"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)

    diagram_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False, index=True)
    diagram: Mapped["Diagram"] = relationship(back_populates="classes")

    atributos: Mapped[List["Atributo"]] = relationship(back_populates="clase", cascade="all, delete-orphan", passive_deletes=True)
    metodos: Mapped[List["Metodo"]] = relationship(back_populates="clase", cascade="all, delete-orphan", passive_deletes=True)



    # Layout en la grilla (compartido por todos los usuarios)
    x_grid:  Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    y_grid:  Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    w_grid:  Mapped[int] = mapped_column(Integer, nullable=False, server_default="12")  # ancho en celdas
    h_grid:  Mapped[int] = mapped_column(Integer, nullable=False, server_default="6")   # alto en celdas
    z_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
 

    # Relaciones donde participa
    outgoing_relations: Mapped[List["Relacion"]] = relationship(
        foreign_keys="Relacion.origen_id", back_populates="origen", passive_deletes=True
    )
    incoming_relations: Mapped[List["Relacion"]] = relationship(
        foreign_keys="Relacion.destino_id", back_populates="destino", passive_deletes=True
    )



# =========================
# Relación
# =========================
class Relacion(Base):
    __tablename__ = "relacion"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diagram_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False, index=True)
    origen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clase.id", ondelete="CASCADE"), nullable=False)
    destino_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clase.id", ondelete="CASCADE"), nullable=False)

    tipo: Mapped[RelType] = mapped_column(Enum(RelType), nullable=False)
    etiqueta: Mapped[Optional[str]] = mapped_column(String(200))

    diagram: Mapped["Diagram"] = relationship(back_populates="relations")
    origen: Mapped["Clase"] = relationship(foreign_keys=[origen_id], back_populates="outgoing_relations")
    destino: Mapped["Clase"] = relationship(foreign_keys=[destino_id], back_populates="incoming_relations")


    src_anchor: Mapped[str] = mapped_column(String(8),  nullable=False, server_default="right")
    dst_anchor: Mapped[str] = mapped_column(String(8),  nullable=False, server_default="left")
    src_offset: Mapped[int] = mapped_column(Integer,    nullable=False, server_default="0")
    dst_offset: Mapped[int] = mapped_column(Integer,    nullable=False, server_default="0")
    src_lane:   Mapped[int] = mapped_column(Integer,    nullable=False, server_default="0")
    dst_lane:   Mapped[int] = mapped_column(Integer,    nullable=False, server_default="0")

# 🔹 Multiplicidad (min/max) por extremo
    mult_origen_min:  Mapped[int]        = mapped_column(Integer, nullable=False, server_default="1")
    mult_origen_max:  Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # NULL = *
    mult_destino_min: Mapped[int]        = mapped_column(Integer, nullable=False, server_default="1")
    mult_destino_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # NULL = *

    # True en las dos relaciones que unen una clase de asociacion (muchos-a-
    # muchos con atributos propios) con las clases originales: el frontend
    # las dibuja punteadas, como corresponde a UML, en vez de como una
    # asociacion solida cualquiera.
    es_clase_asociacion: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")




# =========================
# Atributo
# =========================
class Atributo(Base):
    __tablename__ = "atributo"
    __table_args__ = (
        UniqueConstraint("clase_id", "nombre", name="uq_atributo_clase_nombre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(60), default="string")
    requerido: Mapped[bool] = mapped_column(Boolean, default=False)

    clase_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clase.id", ondelete="CASCADE"), nullable=False)
    clase: Mapped["Clase"] = relationship(back_populates="atributos")


# =========================
# Método
# =========================
class Metodo(Base):
    __tablename__ = "metodo"
    __table_args__ = (
        UniqueConstraint("clase_id", "nombre", name="uq_metodo_clase_nombre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo_retorno: Mapped[str] = mapped_column(String(60), default="void")

    clase_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clase.id", ondelete="CASCADE"), nullable=False)
    clase: Mapped["Clase"] = relationship(back_populates="metodos")

