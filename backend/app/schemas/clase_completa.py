# app/schemas/clase_completa.py
from typing import List, Optional, Union, Literal
from uuid import UUID
from pydantic import BaseModel, Field

RelationType = Literal["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY", "REALIZATION"]
Anchor = Literal["left", "right", "top", "bottom"]

class AtributoOut(BaseModel):
    id: UUID
    name: str = Field(alias="nombre")
    type: str = Field(alias="tipo")
    required: bool = Field(alias="requerido")
    visibility: str = Field(default="-", alias="visibilidad")
    is_static: bool = Field(default=False, alias="es_estatico")
    is_derived: bool = Field(default=False, alias="es_derivado")
    multiplicity: Optional[str] = Field(default=None, alias="multiplicidad")
    default_value: Optional[str] = Field(default=None, alias="valor_inicial")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }

class MetodoOut(BaseModel):
    id: UUID
    name: str = Field(alias="nombre")
    return_type: str = Field(alias="tipo_retorno")
    visibility: str = Field(default="+", alias="visibilidad")
    is_static: bool = Field(default=False, alias="es_estatico")
    is_abstract: bool = Field(default=False, alias="es_abstracto")
    params: str = Field(default="", alias="parametros")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }

class ClaseCompletaOut(BaseModel):
    id: UUID
    name: str = Field(alias="nombre")
    kind: str = Field(default="class", alias="tipo_clase")

    # layout
    x_grid: int
    y_grid: int
    w_grid: int
    h_grid: int
    z_index: int

    # hijos
    atributos: List[AtributoOut] = []
    metodos: List[MetodoOut] = []

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


#schemas exclusivos para recursivos
class ClaseCompletaOutLight(BaseModel):
    id: UUID
    nombre: str
    tipo_clase: str = "class"
    x_grid: int
    y_grid: int
    w_grid: int
    h_grid: int
    z_index: int

    atributos: list[AtributoOut]
    metodos: list[MetodoOut]

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }

class RelacionOutExpanded(BaseModel):
    id: UUID
    type: RelationType = Field(alias="tipo")
    label: Optional[str] = Field(default=None, alias="etiqueta")

    src_anchor: Anchor
    dst_anchor: Anchor
    src_offset: int
    dst_offset: int
    src_lane: int
    dst_lane: int

    src_mult_min: Optional[int] = Field(alias="mult_origen_min")
    src_mult_max: Optional[int] = Field(alias="mult_origen_max")
    dst_mult_min: Optional[int] = Field(alias="mult_destino_min")
    dst_mult_max: Optional[int] = Field(alias="mult_destino_max")

    src_role: Optional[str] = Field(default=None, alias="rol_origen")
    dst_role: Optional[str] = Field(default=None, alias="rol_destino")
    src_navigable: bool = Field(default=False, alias="navegable_origen")
    dst_navigable: bool = Field(default=False, alias="navegable_destino")
    es_clase_asociacion: bool = False

    # 🚀 En vez de solo IDs/nombres, incluyes las clases completas
    origen: ClaseCompletaOutLight
    destino: ClaseCompletaOutLight

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
