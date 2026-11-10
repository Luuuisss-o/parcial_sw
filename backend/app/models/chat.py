# app/models/chat.py
"""
Chat grupal del diagrama (Fase 2, CU-14 / CU-15 / CU-16).

Cada diagrama tiene su propio hilo de mensajes. En la misma tabla conviven:
  - mensajes normales entre colaboradores        (role=USER, asks_ai=False)
  - preguntas dirigidas a la IA ("@IA ...")      (role=USER, asks_ai=True)
  - respuestas de la IA                          (role=ASSISTANT)
  - errores del asistente (cuota, timeout, etc.) (role=ERROR)

Se persiste (en vez de solo reenviarlo por WebSocket) por dos razones:
  1. quien entra tarde al diagrama ve la conversacion previa, y
  2. la IA necesita el historial de cada usuario para responderle con
     coherencia respecto a lo que ese mismo usuario ya le pregunto.
"""
import datetime
import enum
import uuid
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Identity, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ChatRole(str, enum.Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    ERROR = "ERROR"


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diagram_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole, name="chat_role"), nullable=False)

    # Autor humano (NULL en las respuestas de la IA). El nombre y el email se
    # copian al momento de escribir: si despues se borra el usuario, el
    # historial del diagrama sigue siendo legible.
    author_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    author_email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # True si el mensaje es una consulta a la IA.
    asks_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # En respuestas de la IA: a que pregunta responde y a quien va dirigida.
    reply_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True
    )
    addressed_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    addressed_to_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # Como respondio la IA: "MENTOR" (explicacion teorica, sin herramientas,
    # no toca el diagrama) o "AUTO" (pudo editar). NULL en mensajes humanos.
    ai_mode: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # Que modelo genero la respuesta (CU-17): "Gemini (...)", "llama3.2 @ http://...",
    # o el modelo local de un celular. NULL en mensajes humanos.
    ai_model_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Ediciones que la IA aplico sobre el diagrama al responder (si hubo).
    actions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Orden total estable aunque dos mensajes caigan en el mismo instante
    # (la IA puede responder en el mismo milisegundo en que otro escribe).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)

    # Estado de una consulta a la IA (solo preguntas, asks_ai=True):
    # pending -> running -> completed | failed. Persistido para mostrarlo a
    # quien entra tarde, limitar consultas simultaneas y recuperar las que
    # quedaron colgadas si el servidor se reinicio (ver chat_service).
    ai_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Propuesta del asesor que acompaña a esta respuesta (si la hay): viaja
    # con el mensaje, asi quien entra tarde o se reconecta la ve con su estado.
    proposal: Mapped[Optional["AiProposal"]] = relationship(
        "AiProposal",
        primaryjoin="ChatMessage.id == foreign(AiProposal.message_id)",
        uselist=False, viewonly=True, lazy="selectin",
    )


class ProposalStatus(str, enum.Enum):
    PROPOSED = "proposed"   # esperando que alguien la acepte o la rechace
    APPLIED = "applied"     # aceptada y aplicada al diagrama
    REJECTED = "rejected"
    STALE = "stale"         # las clases involucradas cambiaron: no se aplica a ciegas
    FAILED = "failed"       # aceptada, pero alguna operacion fallo al aplicarse


class AiProposal(Base):
    """Cambios que el ASESOR propone (segundo parcial, CU-06/CU-07).

    A diferencia de la IA de edicion (que ejecuta una orden explicita del
    usuario), el asesor solo recomienda: la propuesta queda guardada con sus
    operaciones estructuradas (mismas herramientas que la IA de edicion) y
    una huella de las clases que toca. Un integrante autorizado la acepta o
    la rechaza; al aceptarla se valida contra el diagrama vigente y se
    ejecuta por el mismo servicio de operaciones (DiagramToolExecutor)."""
    __tablename__ = "ai_proposal"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diagram_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True
    )
    # Respuesta del asesor que trae la propuesta (se muestra debajo de ella).
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("chat_message.id", ondelete="CASCADE"), nullable=True, index=True
    )
    requested_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    requested_by_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    requested_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[requested_by_id], lazy="joined")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    operations: Mapped[list] = mapped_column(JSONB, nullable=False)
    base_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=ProposalStatus.PROPOSED.value)
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_by_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
