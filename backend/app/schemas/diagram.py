from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class DiagramCreate(BaseModel):
    title: str

class DiagramUpdate(BaseModel):
    title: Optional[str] = None

class DiagramOut(BaseModel):
    id: UUID
    title: str
    updated_at: datetime
    owner_id: int
    owner_email: str
    ai_solutions_enabled: bool = False
    # Mi rol en este diagrama: OWNER, EDITOR o VIEWER (solo lectura).
    my_role: Optional[str] = None

    model_config = {"from_attributes": True}

class DiagramList(BaseModel):
    items: List[DiagramOut]
    page: int
    limit: int
    total: int
