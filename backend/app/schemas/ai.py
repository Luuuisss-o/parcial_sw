from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AiCommandIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class AiCommandAccepted(BaseModel):
    """El comando quedo encolado; el resultado llega por WebSocket."""
    status: str
    # id del mensaje-pregunta en el chat del diagrama: los eventos ai.* y la
    # respuesta (reply_to_id) lo referencian.
    request_id: Optional[UUID] = None


class AiSettingsOut(BaseModel):
    """Configuracion de la IA en un diagrama (la ve todo el equipo)."""
    solutions_enabled: bool


class AiSettingsIn(BaseModel):
    """Solo el dueño del diagrama puede cambiarla."""
    solutions_enabled: bool
