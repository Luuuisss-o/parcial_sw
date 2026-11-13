from uuid import UUID
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.user import User
from app.models.uml import Diagram, Clase, Atributo, Metodo, Relacion, DiagramCollaborator, CollaboratorRole

READ_ONLY_DETAIL = ("Tenés acceso de solo lectura a este diagrama: "
                    "pedile al dueño que te dé permiso de edición.")


def _accessible_diagram_filter(me: User):
    """Condicion SQL: el diagrama es mio (owner) o soy colaborador."""
    return or_(
        Diagram.owner_id == me.id,
        Diagram.collaborators.any(DiagramCollaborator.user_id == me.id),
    )


def diagram_role(db: Session, user_id: int | None, diagram: Diagram) -> str | None:
    """"OWNER", "EDITOR" o "VIEWER" (colaborador de solo lectura); None si
    no tiene acceso."""
    if user_id is None:
        return None
    if diagram.owner_id == user_id:
        return "OWNER"
    c = (db.query(DiagramCollaborator)
         .filter(DiagramCollaborator.diagram_id == diagram.id, DiagramCollaborator.user_id == user_id)
         .one_or_none())
    if c is None:
        return None
    return "VIEWER" if c.role == CollaboratorRole.VIEWER else "EDITOR"


def can_edit(db: Session, user_id: int | None, diagram: Diagram) -> bool:
    return diagram_role(db, user_id, diagram) in ("OWNER", "EDITOR")


def ensure_can_edit(db: Session, me: User, diagram: Diagram) -> None:
    """403 si el usuario es colaborador de solo lectura. Antes el rol VIEWER
    se podía elegir al invitar pero no se aplicaba: el lector editaba igual."""
    if not can_edit(db, me.id, diagram):
        raise HTTPException(403, READ_ONLY_DETAIL)


def get_my_diagram(db: Session, me: User, diagram_id: UUID, edit: bool = False) -> Diagram:
    """Diagrama al que tengo acceso. edit=True: además tengo que poder
    modificarlo (dueño o colaborador editor)."""
    d = db.query(Diagram).filter(Diagram.id == diagram_id, _accessible_diagram_filter(me)).one_or_none()
    if not d:
        raise HTTPException(404, "Diagrama no encontrado")
    if edit:
        ensure_can_edit(db, me, d)
    return d


def get_my_class(db: Session, me: User, class_id: UUID, edit: bool = False) -> Clase:
    q = (
        db.query(Clase)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(Clase.id == class_id, _accessible_diagram_filter(me))
    )
    c = q.one_or_none()
    if not c:
        raise HTTPException(404, "Clase no encontrada")
    if edit:
        ensure_can_edit(db, me, c.diagram)
    return c


def get_my_attribute(db: Session, me: User, attr_id: UUID, edit: bool = False) -> Atributo:
    a = (
        db.query(Atributo)
        .join(Clase, Clase.id == Atributo.clase_id)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(Atributo.id == attr_id, _accessible_diagram_filter(me))
        .one_or_none()
    )
    if not a:
        raise HTTPException(404, "Atributo no encontrado")
    if edit:
        ensure_can_edit(db, me, a.clase.diagram)
    return a


def get_my_method(db: Session, me: User, method_id: UUID, edit: bool = False) -> Metodo:
    m = (
        db.query(Metodo)
        .join(Clase, Clase.id == Metodo.clase_id)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(Metodo.id == method_id, _accessible_diagram_filter(me))
        .one_or_none()
    )
    if not m:
        raise HTTPException(404, "Metodo no encontrado")
    if edit:
        ensure_can_edit(db, me, m.clase.diagram)
    return m


def get_my_relation(db: Session, me: User, relation_id: UUID, edit: bool = False) -> Relacion:
    r = (
        db.query(Relacion)
        .join(Diagram, Diagram.id == Relacion.diagram_id)
        .filter(Relacion.id == relation_id, _accessible_diagram_filter(me))
        .one_or_none()
    )
    if not r:
        raise HTTPException(404, "Relacion no encontrada")
    if edit:
        ensure_can_edit(db, me, r.diagram)
    return r
