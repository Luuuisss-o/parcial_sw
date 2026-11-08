#app/routers/classes.py
from uuid import UUID
import asyncio, logging
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.uml import Clase, Diagram
from app.schemas.clase import ClaseCreate, ClaseUpdate
from app.schemas.clase_completa import ClaseCompletaOut
from ._helpers import get_my_diagram, get_my_class
from app.utils import realtime_events  # 👈 notificaciones en tiempo real

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagrams", tags=["classes"])


def _ensure_unique_class_name(db: Session, diagram_id: UUID, name: str, exclude_id: UUID | None = None):
    """Valida que no exista otra clase con el mismo nombre en el diagrama."""
    q = db.query(Clase).filter(
        Clase.diagram_id == diagram_id,
        Clase.nombre == name,
    )
    if exclude_id:
        q = q.filter(Clase.id != exclude_id)
    if q.first():
        logger.warning(f"⚠️ Clase duplicada -> diagram_id={diagram_id}, name='{name}'")
        raise HTTPException(
            status_code=400,
            detail=f"La clase '{name}' ya existe en este diagrama"
        )


# 🔹 Crear clase
@router.post("/{diagram_id}/classes", response_model=ClaseCompletaOut, status_code=status.HTTP_201_CREATED)
async def create_class(
    diagram_id: UUID,
    body: ClaseCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"➕ [CREATE] clase -> diagram_id={diagram_id}, user={me.id}, body={body}")
    d = get_my_diagram(db, me, diagram_id)

    _ensure_unique_class_name(db, d.id, body.name)

    # Sin coordenadas (la app movil, o cualquier cliente que no elige la
    # posicion): se ubica en el primer lugar libre de la grilla, igual que las
    # clases que crea la IA. La web siempre manda la posicion del clic.
    x_grid, y_grid = body.x_grid, body.y_grid
    if x_grid is None and y_grid is None:
        from app.services.ai_tools import DiagramToolExecutor
        x_grid, y_grid = DiagramToolExecutor(db, d)._free_slot()

    try:
        c = Clase(
            nombre=body.name,
            diagram_id=d.id,
            x_grid=x_grid or 0,
            y_grid=y_grid or 0,
            w_grid=body.w_grid or 12,
            h_grid=body.h_grid or 6,
            z_index=body.z_index or 0,
        )
        db.add(c); db.commit(); db.refresh(c)
        logger.info(f"✅ Clase creada -> class_id={c.id}, diagram_id={d.id}")

        asyncio.create_task(realtime_events.notify_class_created(d.id, c))
        return c
    except Exception as e:
        logger.error(f"❌ Error creando clase -> diagram_id={diagram_id}, user={me.id}, error={str(e)}")
        raise


# 🔹 Obtener clase por ID
@router.get("/classes/{class_id}", response_model=ClaseCompletaOut)
def get_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"📥 [GET] clase -> class_id={class_id}, user={me.id}")
    c = get_my_class(db, me, class_id)
    if not c:
        logger.warning(f"⚠️ Clase no encontrada -> class_id={class_id}, user={me.id}")
    return c


# 🔹 Listar clases de un diagrama
@router.get("/{diagram_id}/classes", response_model=list[ClaseCompletaOut])
def list_classes(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"📥 [LIST] clases -> diagram_id={diagram_id}, user={me.id}")
    d = get_my_diagram(db, me, diagram_id)
    items = db.query(Clase).filter(Clase.diagram_id == d.id).all()
    logger.info(f"✅ {len(items)} clases encontradas en diagram_id={diagram_id}")
    return items


# 🔹 Actualizar clase
@router.patch("/classes/{class_id}", response_model=ClaseCompletaOut)
async def update_class(
    class_id: UUID,
    body: ClaseUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"✏️ [UPDATE] clase -> class_id={class_id}, user={me.id}, body={body}")
    c = get_my_class(db, me, class_id)

    try:
        if body.name is not None and body.name != c.nombre:
            _ensure_unique_class_name(db, c.diagram_id, body.name, exclude_id=c.id)
            c.nombre = body.name

        if body.x_grid is not None:  c.x_grid  = body.x_grid
        if body.y_grid is not None:  c.y_grid  = body.y_grid
        if body.w_grid is not None:  c.w_grid  = body.w_grid
        if body.h_grid is not None:  c.h_grid  = body.h_grid
        if body.z_index is not None: c.z_index = body.z_index

        db.commit(); db.refresh(c)
        logger.info(f"✅ Clase actualizada -> class_id={c.id}, diagram_id={c.diagram_id}")

        asyncio.create_task(realtime_events.notify_class_updated(c.diagram_id, c))
        return c
    except Exception as e:
        logger.error(f"❌ Error actualizando clase -> class_id={class_id}, error={str(e)}")
        raise


# 🔹 Eliminar clase
@router.delete("/classes/{class_id}", status_code=204)
async def delete_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    logger.info(f"🗑️ [DELETE] clase -> class_id={class_id}, user={me.id}")
    c = get_my_class(db, me, class_id)
    diagram_id = c.diagram_id
    class_id_val = c.id

    try:
        db.delete(c); db.commit()
        logger.info(f"✅ Clase eliminada -> class_id={class_id_val}, diagram_id={diagram_id}")

        asyncio.create_task(realtime_events.notify_class_deleted(diagram_id, class_id_val))
        return
    except Exception as e:
        logger.error(f"❌ Error eliminando clase -> class_id={class_id}, error={str(e)}")
        raise
