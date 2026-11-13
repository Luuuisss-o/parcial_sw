from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID

from .uml_notation import Visibility


def _clean_params(v: Optional[str]) -> Optional[str]:
    """Parámetros como texto UML: "id: Long, nombre: String". Se aceptan
    con o sin paréntesis."""
    if v is None:
        return None
    v = str(v).strip()
    if v.startswith("(") and v.endswith(")"):
        v = v[1:-1].strip()
    if len(v) > 300:
        raise ValueError("los parámetros no pueden superar 300 caracteres")
    return v


class MetodoCreate(BaseModel):
    name: str
    return_type: str = "void"
    # UML 2.5: [visibilidad] nombre(parámetros) : tipo
    visibility: Visibility = "+"
    is_static: bool = False
    is_abstract: bool = False
    params: str = ""

    @field_validator("params")
    @classmethod
    def _params(cls, v):
        return _clean_params(v) or ""


class MetodoUpdate(BaseModel):
    name: Optional[str] = None
    return_type: Optional[str] = None
    visibility: Optional[Visibility] = None
    is_static: Optional[bool] = None
    is_abstract: Optional[bool] = None
    params: Optional[str] = None

    @field_validator("params")
    @classmethod
    def _params(cls, v):
        return _clean_params(v)


class MetodoOut(BaseModel):
    id: UUID
    name: str
    return_type: str
    visibility: str = "+"
    is_static: bool = False
    is_abstract: bool = False
    params: str = ""

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, m) -> "MetodoOut":
        return cls(
            id=m.id,
            name=m.nombre,
            return_type=m.tipo_retorno,
            visibility=m.visibilidad or "+",
            is_static=bool(m.es_estatico),
            is_abstract=bool(m.es_abstracto),
            params=m.parametros or "",
        )
