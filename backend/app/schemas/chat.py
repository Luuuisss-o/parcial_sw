from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.chat import ChatRole

MAX_CHAT_LEN = 4000


class ChatMessageIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_CHAT_LEN)
    # Alternativa explicita a escribir "@IA" en el texto (el boton de la IA
    # del panel lo manda en True). Cualquiera de las dos marca la consulta.
    ask_ai: bool = False

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El mensaje no puede estar vacío")
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

    model_config = {"from_attributes": True}


class ChatHistoryOut(BaseModel):
    items: List[ChatMessageOut]
    # Hay mensajes mas viejos que los devueltos (paginacion hacia atras con ?before_seq=).
    has_more: bool
