from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class AtributoCreate(BaseModel):
    name: str
    type: str
    required: bool = False
    

class AtributoUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    required: Optional[bool] = None

class AtributoOut(BaseModel):
    id: UUID
    name: str
    type: str
    required: bool
    

    model_config = {"from_attributes": True}
