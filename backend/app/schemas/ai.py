from typing import Optional
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AiCommandIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class AiCommandAccepted(BaseModel):
    """El comando quedo encolado; el resultado llega por WebSocket."""
    status: str
    # id del mensaje-pregunta en el chat del diagrama: los eventos ai.* y la
    # respuesta (reply_to_id) lo referencian.
    request_id: Optional[UUID] = None


class AiSettingsOut(BaseModel):
    """Configuracion de la IA en un diagrama (la ve todo el equipo).
    El token del proveedor nunca se devuelve: solo `has_api_key`."""
    enabled: bool = True             # el asesor participa (responde a "@IA")
    mode: str = "on_demand"          # solo responde cuando se lo consulta (no interviene solo)
    proposals_enabled: bool = True   # puede proponer cambios (siempre requieren aceptacion)
    solutions_enabled: bool
    provider: str            # "gemini" | "openai_compatible" | "trained"
    trained_available: bool = False  # el servidor tiene el modelo propio del equipo
    provider_is_default: bool  # True si el diagrama usa el proveedor por defecto del servidor
    model: Optional[str] = None
    base_url: Optional[str] = None
    has_api_key: bool = False
    provider_label: str


class AiSettingsIn(BaseModel):
    """Solo el dueño del diagrama puede cambiarla. Los campos omitidos no se tocan.

    - provider: "gemini", "openai_compatible", o "default" (volver al del servidor).
    - api_key: "" lo borra; omitido, se conserva el guardado.
    """
    enabled: Optional[bool] = None
    proposals_enabled: Optional[bool] = None
    solutions_enabled: Optional[bool] = None
    provider: Optional[Literal["default", "gemini", "openai_compatible", "trained"]] = None
    base_url: Optional[str] = Field(None, max_length=500)
    model: Optional[str] = Field(None, max_length=200)
    api_key: Optional[str] = Field(None, max_length=500)

    @field_validator("base_url")
    @classmethod
    def _url(cls, v):
        if v is None or v == "":
            return v
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("El endpoint debe empezar con http:// o https://")
        return v.rstrip("/")


class AiTestOut(BaseModel):
    ok: bool
    provider_label: str
    detail: str
