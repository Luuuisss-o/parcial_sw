
# app/utils/realtime_events.py
import asyncio
import logging
from uuid import UUID
from app.ws_manager import ws_manager
from app.models.uml import Clase, Atributo, Metodo, Relacion
from app.schemas.relacion import RelacionOut

logger = logging.getLogger(__name__)


def fire(coro):
    """Programa una notificacion realtime sin bloquear al que la dispara.

    Los routers REST son `async def` y ya corren en el loop de FastAPI, asi
    que ahi alcanza con create_task. En cambio el asistente de IA corre en un
    worker thread (endpoint sincrono / BackgroundTask) que no tiene loop
    propio: desde ahi hay que programar la coroutine en el loop principal,
    capturado en el startup de la app, de forma thread-safe.
    """
    try:
        asyncio.get_running_loop()
        asyncio.create_task(coro)
    except RuntimeError:
        loop = ws_manager.main_loop
        if loop is None:
            logger.warning("No se pudo emitir evento realtime: loop principal no capturado aun")
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, loop)


# =========================
# Asistente de IA
# =========================
async def notify_ai_started(diagram_id: UUID, text: str, request_id: str | None = None,
                            requested_by: dict | None = None):
    await ws_manager.broadcast(str(diagram_id), {
        "event": "ai.started",
        "data": {"text": text, "request_id": request_id, "requested_by": requested_by},
    })


async def notify_ai_done(diagram_id: UUID, reply: str, actions: list, request_id: str | None = None,
                         requested_by: dict | None = None, message_id: str | None = None):
    await ws_manager.broadcast(str(diagram_id), {
        "event": "ai.done",
        "data": {
            "reply": reply, "actions": actions, "request_id": request_id,
            "requested_by": requested_by, "message_id": message_id,
        },
    })


async def notify_ai_error(diagram_id: UUID, detail: str, request_id: str | None = None,
                          requested_by: dict | None = None):
    await ws_manager.broadcast(str(diagram_id), {
        "event": "ai.error",
        "data": {"detail": detail, "request_id": request_id, "requested_by": requested_by},
    })


async def notify_ai_settings(diagram_id: UUID, settings: dict):
    """Cambio en la configuracion de la IA del diagrama (lo hace el dueño)."""
    await ws_manager.broadcast(str(diagram_id), {"event": "ai.settings", "data": settings})


# =========================
# Chat grupal y presencia
# =========================
async def notify_chat_message(diagram_id: UUID, message: dict):
    """Un mensaje nuevo en el chat del diagrama (de un colaborador o de la IA)."""
    await ws_manager.broadcast(str(diagram_id), {"event": "chat.message", "data": message})


# =========================
# Clases
# =========================
async def notify_class_created(diagram_id: UUID, clase: Clase):
    payload = {
        "event": "class.created",
        "data": {
            "id": str(clase.id),
            "nombre": clase.nombre,
            "x_grid": clase.x_grid,
            "y_grid": clase.y_grid,
            "w_grid": clase.w_grid,
            "h_grid": clase.h_grid,
            "z_index": clase.z_index,
        },
    }
    print("Evento emitido (Clase Creada):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_class_updated(diagram_id: UUID, clase: Clase):
    payload = {
        "event": "class.updated",
        "data": {
            "id": str(clase.id),
            "nombre": clase.nombre,
            "x_grid": clase.x_grid,
            "y_grid": clase.y_grid,
            "w_grid": clase.w_grid,
            "h_grid": clase.h_grid,
            "z_index": clase.z_index,
        },
    }
    print("Evento emitido (Clase Actualizada):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_class_deleted(diagram_id: UUID, class_id: UUID):
    payload = {
        "event": "class.deleted",
        "data": {"id": str(class_id)},
    }
    print("Evento emitido (Clase Eliminada):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


# =========================
# Atributos
# =========================
async def notify_attribute_created(diagram_id: UUID, atributo: Atributo):
    payload = {
        "event": "attribute.created",
        "data": {
            "id": str(atributo.id),
            "nombre": atributo.nombre,
            "tipo": atributo.tipo,
            "requerido": atributo.requerido,
            "clase_id": str(atributo.clase_id),
        },
    }
    print("Evento emitido (Atributo Creado):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_attribute_updated(diagram_id: UUID, atributo: Atributo):
    payload = {
        "event": "attribute.updated",
        "data": {
            "id": str(atributo.id),
            "nombre": atributo.nombre,
            "tipo": atributo.tipo,
            "requerido": atributo.requerido,
            "clase_id": str(atributo.clase_id),
        },
    }
    print("Evento emitido (Atributo Actualizado):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_attribute_deleted(diagram_id: UUID, atributo_id: UUID, clase_id: UUID):
    payload = {
        "event": "attribute.deleted",
        "data": {
            "id": str(atributo_id),
            "clase_id": str(clase_id),},
    }
    print("Evento emitido (Atributo Eliminado):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


# =========================
# Métodos
# =========================
async def notify_method_created(diagram_id: UUID, metodo: Metodo):
    payload = {
        "event": "method.created",
        "data": {
            "id": str(metodo.id),
            "nombre": metodo.nombre,
            "tipo_retorno": metodo.tipo_retorno,
            "clase_id": str(metodo.clase_id),
        },
    }
    print("Evento emitido (Metodo Creado):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_method_updated(diagram_id: UUID, metodo: Metodo):
    payload = {
        "event": "method.updated",
        "data": {
            "id": str(metodo.id),
            "nombre": metodo.nombre,
            "tipo_retorno": metodo.tipo_retorno,
            "clase_id": str(metodo.clase_id),
        },
    }
    print("Evento emitido (Metodo Actualizado):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_method_deleted(diagram_id: UUID, metodo_id: UUID, clase_id: UUID):
    payload = {
        "event": "method.deleted",
        "data": {
            "id": str(metodo_id),
            "clase_id": str(clase_id), },
    }
    print("Evento emitido (Metodo Eliminado):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)

# =========================
# Relaciones de realtime_events.py
# =========================
async def notify_relation_created(diagram_id: UUID, relation: RelacionOut):
    payload = {
        "event": "relation.created",
        "data": {
            "id": str(relation.id),
            "diagram_id": str(diagram_id),
            "label": relation.label,  # ✅
            "type": relation.type,
            "from_class": str(relation.from_class),
            "to_class": str(relation.to_class),
            "src_anchor": relation.src_anchor,
            "dst_anchor": relation.dst_anchor,
            "src_offset": relation.src_offset,
            "dst_offset": relation.dst_offset,
            "src_lane": relation.src_lane,
            "dst_lane": relation.dst_lane,
            "src_mult_min": relation.src_mult_min,
            "src_mult_max": relation.src_mult_max,
            "dst_mult_min": relation.dst_mult_min,
            "dst_mult_max": relation.dst_mult_max,
            "es_clase_asociacion": relation.es_clase_asociacion,
            "origen_nombre": relation.origen_nombre,
            "destino_nombre": relation.destino_nombre,
        },
    }
    print("Evento emitido (Relacion Creada):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_relation_updated(diagram_id: UUID, relation: RelacionOut):
    payload = {
        "event": "relation.updated",
        "data": {
            "id": str(relation.id),
            "diagram_id": str(diagram_id),
            "label": relation.label,  # ✅
            "type": relation.type,
            "src_anchor": relation.src_anchor,
            "dst_anchor": relation.dst_anchor,
            "src_offset": relation.src_offset,
            "dst_offset": relation.dst_offset,
            "src_lane": relation.src_lane,
            "dst_lane": relation.dst_lane,
            "src_mult_min": relation.src_mult_min,
            "src_mult_max": relation.src_mult_max,
            "dst_mult_min": relation.dst_mult_min,
            "dst_mult_max": relation.dst_mult_max,
            "es_clase_asociacion": relation.es_clase_asociacion,
            "origen_nombre": relation.origen_nombre,
            "destino_nombre": relation.destino_nombre,
        },
    }
    print("Evento emitido (Relacion Actualizada):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)


async def notify_relation_deleted(diagram_id: UUID, relation_id: UUID):
    payload = {
        "event": "relation.deleted",
        # "data": {"id": str(relation_id)},
         "data": {
            "id": str(relation_id),
            "diagram_id": str(diagram_id),
            },
    }
    print("Evento emitido (Relacion Eliminada):", payload)
    await ws_manager.broadcast(str(diagram_id), payload)
