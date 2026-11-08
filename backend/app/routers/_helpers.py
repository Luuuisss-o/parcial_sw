from uuid import UUID
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.user import User
from app.models.uml import Diagram, Clase, Atributo, Metodo, Relacion, DiagramCollaborator


def _accessible_diagram_filter(me: User):
    """Condicion SQL: el diagrama es mio (owner) o soy colaborador."""
    return or_(
        Diagram.owner_id == me.id,
        Diagram.collaborators.any(DiagramCollaborator.user_id == me.id),
    )


def get_my_diagram(db: Session, me: User, diagram_id: UUID) -> Diagram:
    d = db.query(Diagram).filter(Diagram.id == diagram_id, _accessible_diagram_filter(me)).one_or_none()
    if not d:
        raise HTTPException(404, "Diagrama no encontrado")
    return d


def get_my_class(db: Session, me: User, class_id: UUID) -> Clase:
    q = (
        db.query(Clase)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(Clase.id == class_id, _accessible_diagram_filter(me))
    )
    c = q.one_or_none()
    if not c:
        raise HTTPException(404, "Clase no encontrada")
    return c


def get_my_attribute(db: Session, me: User, attr_id: UUID) -> Atributo:
    a = (
        db.query(Atributo)
        .join(Clase, Clase.id == Atributo.clase_id)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(Atributo.id == attr_id, _accessible_diagram_filter(me))
        .one_or_none()
    )
    if not a:
        raise HTTPException(404, "Atributo no encontrado")
    return a


def get_my_method(db: Session, me: User, method_id: UUID) -> Metodo:
    m = (
        db.query(Metodo)
        .join(Clase, Clase.id == Metodo.clase_id)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(Metodo.id == method_id, _accessible_diagram_filter(me))
        .one_or_none()
    )
    if not m:
        raise HTTPException(404, "Metodo no encontrado")
    return m


def get_my_relation(db: Session, me: User, relation_id: UUID) -> Relacion:
    r = (
        db.query(Relacion)
        .join(Diagram, Diagram.id == Relacion.diagram_id)
        .filter(Relacion.id == relation_id, _accessible_diagram_filter(me))
        .one_or_none()
    )
    if not r:
        raise HTTPException(404, "Relacion no encontrada")
    return r
