from pydantic import BaseModel
from typing import List, Optional


class DetectedAttribute(BaseModel):
    name: str
    type: str = "string"
    required: bool = False


class DetectedClass(BaseModel):
    name: str
    attributes: List[DetectedAttribute] = []


class DetectedRelation(BaseModel):
    from_class: str
    to_class: str
    type: str = "ASSOCIATION"
    label: Optional[str] = None
    src_multiplicity: Optional[str] = None
    dst_multiplicity: Optional[str] = None


class VisionDetectResult(BaseModel):
    """Lo que Gemini leyó de la foto, todavía sin aplicar a ningún diagrama:
    el usuario la revisa y corrige en el frontend antes de confirmar."""
    classes: List[DetectedClass] = []
    relations: List[DetectedRelation] = []
    warning: Optional[str] = None


class VisionApplyIn(BaseModel):
    """Lo mismo que VisionDetectResult, pero ya revisado/editado por el
    usuario: es lo que se termina creando en el diagrama nuevo."""
    title: str = "Diagrama importado"
    classes: List[DetectedClass] = []
    relations: List[DetectedRelation] = []


class VisionApplySummary(BaseModel):
    diagram_id: str
    classes_created: List[str] = []
    attributes_created: int = 0
    relations_created: int = 0
    warnings: List[str] = []
