# app/routers/diagramas.py
# POST
# http://localhost:8000/diagrams
# {
#   "title": "Mi primer diagrama"
# } 
# GET
# http://localhost:8000/diagrams?page=1&limit=20
from uuid import UUID
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.uml import Clase, Relacion, DiagramCollaborator, CollaboratorRole
from app.models.uml import Diagram
from app.schemas.diagram import DiagramCreate, DiagramOut, DiagramList
from app.schemas.collaborator import CollaboratorCreate, CollaboratorOut
from app.schemas.clase_completa import ClaseCompletaOut, ClaseCompletaOutLight,RelacionOutExpanded

from app.utils import realtime_events
from ._helpers import get_my_diagram, _accessible_diagram_filter, diagram_role

router = APIRouter(prefix="/diagrams", tags=["diagrams"])
log = logging.getLogger("app.routers.diagramas")


@router.post("", response_model=DiagramOut, status_code=status.HTTP_201_CREATED)
def create_diagram(
    body: DiagramCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    log.info(f"➕ Crear diagrama -> user_id={me.id}, title={body.title}")
    d = Diagram(title=body.title, owner_id=me.id)
    db.add(d); db.commit(); db.refresh(d)
    log.debug(f"✅ Diagrama creado -> id={d.id}, title={d.title}")
    return d


@router.get("", response_model=DiagramList)
def list_diagrams(
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if page < 1: page = 1
    if limit < 1: limit = 20

    log.info(f"📥 Listar diagramas -> user_id={me.id}, page={page}, limit={limit}")

    q = db.query(Diagram).filter(_accessible_diagram_filter(me)).order_by(Diagram.updated_at.desc())
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()

    log.debug(f"✅ {len(items)} diagramas obtenidos de un total de {total}")
    out = []
    for d in items:
        o = DiagramOut.model_validate(d)
        o.my_role = diagram_role(db, me.id, d)
        out.append(o)
    return DiagramList(items=out, page=page, limit=limit, total=total)


@router.get("/{diagram_id}", response_model=DiagramOut)
def get_diagram(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    log.info(f"🔍 Obtener diagrama -> user_id={me.id}, diagram_id={diagram_id}")
    d = db.query(Diagram).filter(Diagram.id == diagram_id, _accessible_diagram_filter(me)).one_or_none()
    if not d:
        log.warning(f"⚠️ Diagrama no encontrado -> diagram_id={diagram_id}, user_id={me.id}")
        raise HTTPException(404, "Diagrama no encontrado")
    log.debug(f"✅ Diagrama encontrado -> id={d.id}, title={d.title}")
    out = DiagramOut.model_validate(d)
    out.my_role = diagram_role(db, me.id, d)
    return out


@router.delete("/{diagram_id}", status_code=204)
def delete_diagram(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    log.info(f"🗑️ Eliminar diagrama -> user_id={me.id}, diagram_id={diagram_id}")
    d = db.query(Diagram).filter(Diagram.id == diagram_id, Diagram.owner_id == me.id).one_or_none()
    if not d:
        log.warning(f"⚠️ Intento de eliminar diagrama inexistente -> diagram_id={diagram_id}, user_id={me.id}")
        raise HTTPException(404, "Diagrama no encontrado")

    db.delete(d); db.commit()
    log.debug(f"✅ Diagrama eliminado -> id={diagram_id}, user_id={me.id}")
    return


@router.get("/{diagram_id}/full", response_model=dict)
def get_diagram_full(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    d = get_my_diagram(db, me, diagram_id)

    # Todas las clases con atributos y métodos
    clases = db.query(Clase).filter(Clase.diagram_id == d.id).all()
    clases_out = [ClaseCompletaOut.model_validate(c) for c in clases]

    # Todas las relaciones expandidas
    relaciones = db.query(Relacion).filter(Relacion.diagram_id == d.id).all()
    relaciones_out = []
    for r in relaciones:
        relaciones_out.append(
            RelacionOutExpanded.model_validate({
                **r.__dict__,
                "origen": ClaseCompletaOutLight.model_validate(r.origen),
                "destino": ClaseCompletaOutLight.model_validate(r.destino),
            })
        )

    return {
        "id": str(d.id),
        "title": d.title,
        "clases": clases_out,
        "relaciones": relaciones_out
    }


@router.get("/{diagram_id}/collaborators", response_model=list[CollaboratorOut])
def list_collaborators(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    d = get_my_diagram(db, me, diagram_id)
    rows = (
        db.query(DiagramCollaborator)
        .filter(DiagramCollaborator.diagram_id == d.id)
        .all()
    )
    return [
        CollaboratorOut(id=r.id, user_id=r.user_id, email=r.user.email, name=r.user.name, role=r.role)
        for r in rows
    ]


@router.post("/{diagram_id}/collaborators", response_model=CollaboratorOut, status_code=status.HTTP_201_CREATED)
def add_collaborator(
    diagram_id: UUID,
    body: CollaboratorCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    # Solo el dueño decide quién puede entrar al diagrama.
    d = db.query(Diagram).filter(Diagram.id == diagram_id, Diagram.owner_id == me.id).one_or_none()
    if not d:
        raise HTTPException(404, "Diagrama no encontrado")

    # Sin distinguir mayúsculas ni espacios: "Diego@Mail.com " es la misma cuenta.
    target = db.query(User).filter(func.lower(User.email) == body.email.strip().lower()).one_or_none()
    if not target:
        raise HTTPException(404, "No existe ningún usuario con ese email")
    if target.id == d.owner_id:
        raise HTTPException(400, "El dueño ya tiene acceso al diagrama")

    existing = (
        db.query(DiagramCollaborator)
        .filter(DiagramCollaborator.diagram_id == d.id, DiagramCollaborator.user_id == target.id)
        .one_or_none()
    )
    if existing:
        existing.role = body.role
        db.commit(); db.refresh(existing)
        realtime_events.fire(realtime_events.notify_collaborators_changed(d.id, target.email, existing.role.value))
        return CollaboratorOut(id=existing.id, user_id=target.id, email=target.email, name=target.name, role=existing.role)

    collab = DiagramCollaborator(diagram_id=d.id, user_id=target.id, role=body.role)
    db.add(collab); db.commit(); db.refresh(collab)
    realtime_events.fire(realtime_events.notify_collaborators_changed(d.id, target.email, collab.role.value))
    return CollaboratorOut(id=collab.id, user_id=target.id, email=target.email, name=target.name, role=collab.role)


@router.delete("/{diagram_id}/collaborators/{user_id}", status_code=204)
def remove_collaborator(
    diagram_id: UUID,
    user_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    d = db.query(Diagram).filter(Diagram.id == diagram_id, Diagram.owner_id == me.id).one_or_none()
    if not d:
        raise HTTPException(404, "Diagrama no encontrado")

    collab = (
        db.query(DiagramCollaborator)
        .filter(DiagramCollaborator.diagram_id == d.id, DiagramCollaborator.user_id == user_id)
        .one_or_none()
    )
    if not collab:
        raise HTTPException(404, "Ese usuario no es colaborador de este diagrama")

    removed_email = collab.user.email if getattr(collab, 'user', None) else ''
    db.delete(collab); db.commit()
    realtime_events.fire(realtime_events.notify_collaborators_changed(d.id, removed_email, None))
    return
