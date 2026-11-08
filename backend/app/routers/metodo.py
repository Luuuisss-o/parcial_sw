
# app/routers/metodo.py
from uuid import UUID
import logging, asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.uml import Metodo, Clase, Diagram
from app.schemas.metodo import MetodoCreate, MetodoUpdate, MetodoOut
from ._helpers import get_my_class, get_my_method
from app.utils import realtime_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagrams", tags=["methods"])


def _ensure_unique_method_name(db: Session, clase_id: UUID, name: str, exclude_id: UUID | None = None):
    """Valida que no exista otro metodo con el mismo nombre en la clase."""
    q = db.query(Metodo).filter(
        Metodo.clase_id == clase_id,
        Metodo.nombre == name,
    )
    if exclude_id:
        q = q.filter(Metodo.id != exclude_id)
    if q.first():
        raise HTTPException(
            status_code=400,
            detail=f"La clase ya tiene un metodo llamado '{name}'"
        )


# 🔹 Listar métodos
@router.get("/classes/{class_id}/methods", response_model=list[MetodoOut])
def list_methods(
    class_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"📥 [LIST] métodos -> class_id={class_id}, user={me.id}")
    c = get_my_class(db, me, class_id)
    items = db.query(Metodo).filter(Metodo.clase_id == c.id).all()
    logger.info(f"✅ {len(items)} métodos encontrados en class_id={class_id}")
    return [MetodoOut(id=i.id, name=i.nombre, return_type=i.tipo_retorno) for i in items]


# 🔹 Crear método
@router.post("/classes/{class_id}/methods", response_model=MetodoOut, status_code=status.HTTP_201_CREATED)
async def create_method(
    class_id: UUID,
    body: MetodoCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"➕ [CREATE] método -> class_id={class_id}, user={me.id}, body={body}")
    c = get_my_class(db, me, class_id)
    _ensure_unique_method_name(db, c.id, body.name)

    try:
        m = Metodo(nombre=body.name, tipo_retorno=body.return_type, clase_id=c.id)
        db.add(m); db.commit(); db.refresh(m)
        logger.info(f"✅ Método creado -> method_id={m.id}, class_id={c.id}")

        # 🔔 Notificar en tiempo real
        asyncio.create_task(realtime_events.notify_method_created(c.diagram_id, m))
        asyncio.create_task(realtime_events.notify_class_updated(c.diagram_id, c))
        return MetodoOut(id=m.id, name=m.nombre, return_type=m.tipo_retorno)
    except Exception as e:
        logger.error(f"❌ Error creando método -> class_id={class_id}, error={str(e)}")
        raise


# 🔹 Actualizar método
@router.patch("/methods/{method_id}", response_model=MetodoOut)
async def update_method(
    method_id: UUID,
    body: MetodoUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"✏️ [UPDATE] método -> method_id={method_id}, user={me.id}, body={body}")
    m = get_my_method(db, me, method_id)

    try:
        if body.name is not None and body.name != m.nombre:
            _ensure_unique_method_name(db, m.clase_id, body.name, exclude_id=m.id)
            m.nombre = body.name
        if body.return_type is not None: m.tipo_retorno = body.return_type

        db.commit(); db.refresh(m)
        c = m.clase
        logger.info(f"✅ Método actualizado -> method_id={m.id}, class_id={c.id}")

        # 🔔 Notificar en tiempo real
        asyncio.create_task(realtime_events.notify_method_updated(c.diagram_id, m))
        asyncio.create_task(realtime_events.notify_class_updated(c.diagram_id, c))
        return MetodoOut(id=m.id, name=m.nombre, return_type=m.tipo_retorno)
    except Exception as e:
        logger.error(f"❌ Error actualizando método -> method_id={method_id}, error={str(e)}")
        raise


# 🔹 Eliminar método
@router.delete("/methods/{method_id}", response_model=dict)
async def delete_method(
    method_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"🗑️ [DELETE] método -> method_id={method_id}, user={me.id}")
    m = get_my_method(db, me, method_id)

    try:
        c = m.clase
        method_id = m.id
        db.delete(m); db.commit()
        logger.info(f"✅ Método eliminado -> method_id={method_id}, class_id={c.id}")

        # 🔔 Notificar en tiempo real
        asyncio.create_task(realtime_events.notify_method_deleted(c.diagram_id, method_id, c.id))
        asyncio.create_task(realtime_events.notify_class_updated(c.diagram_id, c))
        return {"id": str(method_id), "class_id": str(c.id)}
    except Exception as e:
        logger.error(f"❌ Error eliminando método -> method_id={method_id}, error={str(e)}")
        raise
