from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID

from .uml_notation import Visibility, normalize_multiplicity, clean_optional_text


class AtributoCreate(BaseModel):
    name: str
    type: str
    required: bool = False
    # UML 2.5: [visibilidad] [/]nombre : tipo [multiplicidad] [= valor]
    visibility: Visibility = "-"
    is_static: bool = False
    is_derived: bool = False
    multiplicity: Optional[str] = None
    default_value: Optional[str] = None

    @field_validator("multiplicity")
    @classmethod
    def _mult(cls, v):
        return normalize_multiplicity(v)

    @field_validator("default_value")
    @classmethod
    def _default(cls, v):
        return clean_optional_text(v)


class AtributoUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    required: Optional[bool] = None
    visibility: Optional[Visibility] = None
    is_static: Optional[bool] = None
    is_derived: Optional[bool] = None
    # "" o null explícito borran la multiplicidad / el valor inicial
    multiplicity: Optional[str] = None
    default_value: Optional[str] = None

    @field_validator("multiplicity")
    @classmethod
    def _mult(cls, v):
        return normalize_multiplicity(v)

    @field_validator("default_value")
    @classmethod
    def _default(cls, v):
        return clean_optional_text(v)


class AtributoOut(BaseModel):
    id: UUID
    name: str
    type: str
    required: bool
    visibility: str = "-"
    is_static: bool = False
    is_derived: bool = False
    multiplicity: Optional[str] = None
    default_value: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, a) -> "AtributoOut":
        return cls(
            id=a.id,
            name=a.nombre,
            type=a.tipo,
            required=a.requerido,
            visibility=a.visibilidad or "-",
            is_static=bool(a.es_estatico),
            is_derived=bool(a.es_derivado),
            multiplicity=a.multiplicidad,
            default_value=a.valor_inicial,
        )
