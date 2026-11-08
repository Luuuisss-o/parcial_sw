from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from typing import List
from .atributo import AtributoOut
from .metodo import MetodoOut

class ClaseCreate(BaseModel):
    # nombre visible en la API
    name: str
    # opcionales para layout inicial (si no envías, usan server_default del modelo)
    x_grid: Optional[int] = None
    y_grid: Optional[int] = None
    w_grid: Optional[int] = None
    h_grid: Optional[int] = None
    z_index: Optional[int] = None


class ClaseUpdate(BaseModel):
    # parches opcionales
    name: Optional[str] = None
    x_grid: Optional[int] = None
    y_grid: Optional[int] = None
    w_grid: Optional[int] = None
    h_grid: Optional[int] = None
    z_index: Optional[int] = None


class ClaseOut(BaseModel):
    id: UUID
    # el modelo tiene "nombre" → exponemos "name"
    name: str = Field(alias="nombre")

    # layout
    x_grid: int
    y_grid: int
    w_grid: int
    h_grid: int
    z_index: int
 
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,  # por si un día quieres construir desde "name"
    }
