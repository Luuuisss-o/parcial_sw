from pydantic import BaseModel


class AiCommandIn(BaseModel):
    text: str


class AiCommandAccepted(BaseModel):
    """El comando quedo encolado; el resultado llega por WebSocket."""
    status: str
