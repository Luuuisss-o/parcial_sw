# app/schemas/clase_completa.py
from typing import List, Optional, Union, Literal
from uuid import UUID
from pydantic import BaseModel, Field

RelationType = Literal["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"]
Anchor = Literal["left", "right", "top", "bottom"]

class AtributoOut(BaseModel):
    id: UUID
    name: str = Field(alias="nombre")
    type: str = Field(alias="tipo")
    required: bool = Field(alias="requerido")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }

class MetodoOut(BaseModel):
    id: UUID
    name: str = Field(alias="nombre")
    return_type: str = Field(alias="tipo_retorno")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }

class ClaseCompletaOut(BaseModel):
    id: UUID
    name: str = Field(alias="nombre")

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

    # 🚀 En vez de solo IDs/nombres, incluyes las clases completas
    origen: ClaseCompletaOutLight
    destino: ClaseCompletaOutLight

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
