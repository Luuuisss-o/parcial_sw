from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class MetodoCreate(BaseModel):
    name: str
    return_type: str = "void"

class MetodoUpdate(BaseModel):
    name: Optional[str] = None
    return_type: Optional[str] = None

class MetodoOut(BaseModel):
    id: UUID
    name: str
    return_type: str

    model_config = {"from_attributes": True}
