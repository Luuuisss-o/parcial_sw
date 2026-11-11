
# app/routers/relacion.py
from uuid import UUID
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.uml import Diagram, Clase, Relacion, RelType
from app.schemas.relacion import RelacionCreate, RelacionUpdate, RelacionOut
from ._helpers import get_my_diagram, get_my_relation, _accessible_diagram_filter
from app.utils import realtime_events  # 👈 notificaciones en tiempo real
from app.schemas.relacion import RelacionOut

router = APIRouter(prefix="/diagrams", tags=["relations"])
logger = logging.getLogger(__name__)


def _ctx(**kw) -> str:
    """Formatea contexto k=v para logs compactos."""
    return " ".join(f"{k}={v}" for k, v in kw.items() if v is not None)


def _get_class_in_my_diagram(
    db: Session, me: User, diagram_id: UUID, class_id: UUID
) -> Clase | None:
    return (
        db.query(Clase)
        .join(Diagram, Diagram.id == Clase.diagram_id)
        .filter(
            Clase.id == class_id,
            Clase.diagram_id == diagram_id,
            _accessible_diagram_filter(me),
        )
        .one_or_none()
    )


# 🔹 Crear relación
@router.post("/{diagram_id}/relations", response_model=RelacionOut, status_code=status.HTTP_201_CREATED)
async def create_relation(
    diagram_id: UUID,
    body: RelacionCreate,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"➕ [CREATE] relación -> diagram_id={diagram_id}, user={me.id}, body={body}")

    d = get_my_diagram(db, me, diagram_id)
    src = _get_class_in_my_diagram(db, me, d.id, body.from_class)
    dst = _get_class_in_my_diagram(db, me, d.id, body.to_class)

    if not src or not dst:
        logger.warning(f"⚠️ Clase origen o destino no encontrada -> diagram_id={diagram_id}, user={me.id}")
        raise HTTPException(404, detail="Clase origen/destino no encontrada en el diagrama")

    try:
        r = Relacion(
            diagram_id=d.id,
            origen_id=src.id,
            destino_id=dst.id,
            tipo=RelType(body.type),
            etiqueta=body.label,
            src_anchor=body.src_anchor,
            dst_anchor=body.dst_anchor,
            src_offset=body.src_offset,
            dst_offset=body.dst_offset,
            src_lane=body.src_lane,
            dst_lane=body.dst_lane,
            mult_origen_min=body.src_mult_min,
            mult_origen_max=body.src_mult_max,
            mult_destino_min=body.dst_mult_min,
            mult_destino_max=body.dst_mult_max,
            es_clase_asociacion=body.es_clase_asociacion,
            rol_origen=body.src_role,
            rol_destino=body.dst_role,
            navegable_origen=body.src_navigable,
            navegable_destino=body.dst_navigable,
        )
        db.add(r)
        d.updated_at = func.now()
        db.commit(); db.refresh(r)

        rel_out = RelacionOut.model_validate({
            **r.__dict__,
            "origen_nombre": src.nombre,
            "destino_nombre": dst.nombre,
        })

        asyncio.create_task(realtime_events.notify_relation_created(d.id, rel_out))
        logger.info(f"✅ Relación creada -> relation_id={r.id}, diagram_id={d.id}")
        return rel_out
    except Exception as e:
        logger.error(f"❌ Error creando relación -> diagram_id={diagram_id}, error={str(e)}")
        raise


# 🔹 Listar relaciones de un diagrama
@router.get("/{diagram_id}/relations", response_model=list[RelacionOut])
def list_relations(
    diagram_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"📥 [LIST] relaciones -> diagram_id={diagram_id}, user={me.id}")
    d = get_my_diagram(db, me, diagram_id)

    Origen = aliased(Clase)
    Destino = aliased(Clase)

    items = (
        db.query(
            Relacion,
            Origen.nombre.label("origen_nombre"),
            Destino.nombre.label("destino_nombre"),
        )
        .join(Origen, Relacion.origen_id == Origen.id)
        .join(Destino, Relacion.destino_id == Destino.id)
        .filter(Relacion.diagram_id == d.id)
        .all()
    )

    logger.info(f"✅ {len(items)} relaciones encontradas en diagram_id={diagram_id}")
    result = []
    for rel, origen_nombre, destino_nombre in items:
        result.append(
            RelacionOut.model_validate(
                {**rel.__dict__, "origen_nombre": origen_nombre, "destino_nombre": destino_nombre}
            )
        )
    return result


# 🔹 Actualizar relación
@router.patch("/relations/{relation_id}", response_model=RelacionOut)
async def update_relation(
    relation_id: UUID,
    body: RelacionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"✏️ [UPDATE] relación -> relation_id={relation_id}, user={me.id}, body={body}")
    r = get_my_relation(db, me, relation_id)

    try:
        # ⚡️ Campos normales
        if "type" in body.__fields_set__:
            r.tipo = RelType(body.type)
        if "label" in body.__fields_set__:
            r.etiqueta = body.label
        if "src_anchor" in body.__fields_set__:
            r.src_anchor = body.src_anchor
        if "dst_anchor" in body.__fields_set__:
            r.dst_anchor = body.dst_anchor
        if "src_offset" in body.__fields_set__:
            r.src_offset = body.src_offset
        if "dst_offset" in body.__fields_set__:
            r.dst_offset = body.dst_offset
        if "src_lane" in body.__fields_set__:
            r.src_lane = body.src_lane
        if "dst_lane" in body.__fields_set__:
            r.dst_lane = body.dst_lane

        # ⚡️ Multiplicidad (acepta null explícito)
        if "src_mult_min" in body.__fields_set__:
            r.mult_origen_min = body.src_mult_min
        if "src_mult_max" in body.__fields_set__:
            r.mult_origen_max = body.src_mult_max
        if "dst_mult_min" in body.__fields_set__:
            r.mult_destino_min = body.dst_mult_min
        if "dst_mult_max" in body.__fields_set__:
            r.mult_destino_max = body.dst_mult_max

        # ⚡️ Roles y navegabilidad (UML 2.5)
        if "src_role" in body.__fields_set__:
            r.rol_origen = body.src_role
        if "dst_role" in body.__fields_set__:
            r.rol_destino = body.dst_role
        if body.src_navigable is not None:
            r.navegable_origen = body.src_navigable
        if body.dst_navigable is not None:
            r.navegable_destino = body.dst_navigable
        r.diagram.updated_at = func.now()
        db.commit(); db.refresh(r)

        origen_nombre = db.query(Clase.nombre).filter(Clase.id == r.origen_id).scalar()
        destino_nombre = db.query(Clase.nombre).filter(Clase.id == r.destino_id).scalar()

        rel_out = RelacionOut.model_validate({
            **r.__dict__,
            "origen_nombre": origen_nombre,
            "destino_nombre": destino_nombre,
        })

        asyncio.create_task(realtime_events.notify_relation_updated(r.diagram_id, rel_out))
        logger.info(f"✅ Relación actualizada -> relation_id={r.id}, diagram_id={r.diagram_id}")
        return rel_out
    except Exception as e:
        logger.error(f"❌ Error actualizando relación -> relation_id={relation_id}, error={str(e)}")
        raise


# 🔹 Eliminar relación
@router.delete("/relations/{relation_id}", status_code=204)
async def delete_relation(
    relation_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"🗑️ [DELETE] relación -> relation_id={relation_id}, user={me.id}")
    r = get_my_relation(db, me, relation_id)

    try:
        diagram_id = r.diagram_id
        relation_id_value = r.id

        r.diagram.updated_at = func.now()
        db.delete(r); db.commit()

        asyncio.create_task(realtime_events.notify_relation_deleted(diagram_id, relation_id_value))
        logger.info(f"✅ Relación eliminada -> relation_id={relation_id_value}, diagram_id={diagram_id}")
        return
    except Exception as e:
        logger.error(f"❌ Error eliminando relación -> relation_id={relation_id}, error={str(e)}")
        raise


@router.get("/relations/{relation_id}", response_model=dict)
def get_relation(
    relation_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    r = get_my_relation(db, me, relation_id)

    origen_nombre = db.query(Clase.nombre).filter(Clase.id == r.origen_id).scalar()
    destino_nombre = db.query(Clase.nombre).filter(Clase.id == r.destino_id).scalar()

    return {
        "id": str(r.id),
        "diagram_id": str(r.diagram_id),
        "from_class": str(r.origen_id),
        "to_class": str(r.destino_id),
        "type": r.tipo,               # 👈 traducido
        "label": r.etiqueta,          # 👈 traducido
        "src_anchor": r.src_anchor,
        "dst_anchor": r.dst_anchor,
        "src_offset": r.src_offset,
        "dst_offset": r.dst_offset,
        "src_lane": r.src_lane,
        "dst_lane": r.dst_lane,
        "src_mult_min": r.mult_origen_min,  # 👈 traducido
        "src_mult_max": r.mult_origen_max,
        "dst_mult_min": r.mult_destino_min,
        "dst_mult_max": r.mult_destino_max,
        "es_clase_asociacion": r.es_clase_asociacion,
        "src_role": r.rol_origen,
        "dst_role": r.rol_destino,
        "src_navigable": r.navegable_origen,
        "dst_navigable": r.navegable_destino,
        "origen_nombre": origen_nombre,
        "destino_nombre": destino_nombre,
    }
