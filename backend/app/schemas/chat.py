from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.chat import ChatRole

MAX_CHAT_LEN = 4000


class ChatMessageIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_CHAT_LEN)
    # Alternativa explicita a escribir "@IA" en el texto (el boton de la IA
    # del panel lo manda en True). Cualquiera de las dos marca la consulta.
    ask_ai: bool = False
    # La consulta la responde el modelo local del CELULAR de quien pregunta
    # (no el servidor): ver POST /chat/{id}/answer.
    answer_on_device: bool = False

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El mensaje no puede estar vacío")
        return v


class ProposalOut(BaseModel):
    """Propuesta del asesor (segundo parcial). `changes` es el texto legible
    de cada operacion, para mostrar el impacto antes de aceptarla."""
    id: UUID
    message_id: Optional[UUID] = None
    status: str  # proposed | applying | applied | rejected | stale | failed
    summary: str
    operations: list
    changes: List[str]
    requested_by_id: Optional[int] = None
    requested_by_name: Optional[str] = None
    requested_by_email: Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    result: Optional[list] = None

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, v):
        if hasattr(v, "operations") and not isinstance(v, dict):
            from app.services.ai_proposals import payload
            return payload(v)
        return v


class ChatMessageOut(BaseModel):
    id: UUID
    diagram_id: UUID
    role: ChatRole
    author_id: Optional[int] = None
    author_name: str
    author_email: Optional[str] = None
    content: str
    asks_ai: bool
    reply_to_id: Optional[UUID] = None
    addressed_to_id: Optional[int] = None
    addressed_to_name: Optional[str] = None
    ai_mode: Optional[str] = None
    ai_model_label: Optional[str] = None
    actions: Optional[list] = None
    created_at: datetime
    seq: int
    ai_status: Optional[str] = None  # solo preguntas a la IA: pending|running|completed|failed
    proposal: Optional[ProposalOut] = None

    model_config = {"from_attributes": True}


class ChatHistoryOut(BaseModel):
    items: List[ChatMessageOut]
    # Hay mensajes mas viejos que los devueltos (paginacion hacia atras con ?before_seq=).
    has_more: bool


class DeviceAnswerIn(BaseModel):
    """Respuesta que generó el modelo local del celular de quien preguntó."""
    content: Optional[str] = Field(None, max_length=MAX_CHAT_LEN)
    error: Optional[str] = Field(None, max_length=1000)
    actions: Optional[list] = None
    # Cambios que el modelo del celular PROPONE como asesor (no los aplico):
    # el servidor los valida y, si el diagrama lo permite, quedan como propuesta.
    proposed_actions: Optional[list] = None
    ai_mode: Optional[str] = Field(None, pattern="^(AUTO|MENTOR)$")
    model_label: Optional[str] = Field(None, max_length=200)


class AiContextOut(BaseModel):
    """Contexto que el celular necesita para responder con su modelo local:
    el mismo que arma el servidor para Gemini (memoria hibrida)."""
    question_id: UUID
    question: str
    requester_name: str
    requester_email: Optional[str] = None
    history: List[dict]        # [{question, answer}] del mismo usuario
    team_context: List[dict]   # [{author, content, is_ai, addressed_to}]
    diagram: dict              # snapshot (clases, atributos, metodos, relaciones)
    solutions_enabled: bool
    mode: str                  # "MENTOR" | "AUTO" (clasificacion del servidor)
