from pydantic import BaseModel
from typing import List
from uuid import UUID
from app.models.uml import CollaboratorRole


class CollaboratorCreate(BaseModel):
    email: str
    role: CollaboratorRole = CollaboratorRole.EDITOR


class CollaboratorOut(BaseModel):
    id: UUID
    user_id: int
    email: str
    name: str
    role: CollaboratorRole

    model_config = {"from_attributes": True}


class CollaboratorList(BaseModel):
    items: List[CollaboratorOut]
