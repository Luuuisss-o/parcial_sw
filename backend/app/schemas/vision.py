from pydantic import BaseModel
from typing import List, Optional


class DetectedAttribute(BaseModel):
    name: str
    type: str = "string"
    required: bool = False
    # Notación UML 2.5
    visibility: str = "-"
    is_static: bool = False
    is_derived: bool = False
    multiplicity: Optional[str] = None
    default_value: Optional[str] = None


class DetectedMethod(BaseModel):
    name: str
    params: str = ""
    return_type: str = "void"
    visibility: str = "+"
    is_static: bool = False
    is_abstract: bool = False


class DetectedClass(BaseModel):
    name: str
    kind: str = "class"  # class | abstract | interface | enumeration
    attributes: List[DetectedAttribute] = []
    methods: List[DetectedMethod] = []


class DetectedRelation(BaseModel):
    from_class: str
    to_class: str
    type: str = "ASSOCIATION"
    label: Optional[str] = None
    src_multiplicity: Optional[str] = None
    dst_multiplicity: Optional[str] = None
    src_role: Optional[str] = None
    dst_role: Optional[str] = None
    src_navigable: bool = False
    dst_navigable: bool = False


class VisionDetectResult(BaseModel):
    """Lo que Gemini leyó de la foto, todavía sin aplicar a ningún diagrama:
    el usuario la revisa y corrige en el frontend antes de confirmar."""
    source: str = "uml"  # "uml" (diagrama de clases) o "er" (base de datos)
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
    methods_created: int = 0
    relations_created: int = 0
    warnings: List[str] = []
