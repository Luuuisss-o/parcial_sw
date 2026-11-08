# app/routers/realtime.py
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from app.core.security import decode_token
from app.db import SessionLocal
from app.models.uml import Diagram, DiagramCollaborator
from app.models.user import User
from app.services.locks import lock_manager
from app.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagrams", tags=["realtime"])


def _authenticate(token: str | None, diagram_id: str) -> tuple[str, str, int] | None:
    """Valida el token y que el diagrama exista y le pertenezca al usuario.
    Devuelve (email, nombre, user_id) si esta todo bien, None si hay que
    rechazar la conexion.

    El WebSocket nativo del navegador no permite mandar headers custom, asi
    que el token viaja por query string (?token=...) en vez del header
    Authorization que usa el resto de la API.
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("kind") != "access":
            return None
        email = payload.get("sub")
        if not email:
            return None
    except JWTError:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one_or_none()
        if not user or not user.active:
            return None
        try:
            diag_uuid = UUID(diagram_id)
        except ValueError:
            return None
        diagram = (
            db.query(Diagram)
            .filter(
                Diagram.id == diag_uuid,
                (Diagram.owner_id == user.id)
                | Diagram.collaborators.any(DiagramCollaborator.user_id == user.id),
            )
            .one_or_none()
        )
        if not diagram:
            return None
        return email, user.name, user.id
    finally:
        db.close()


# Paleta fija para asignarle un color estable a cada cursor: se elige por
# hash del email, asi la misma persona siempre tiene el mismo color en
# cualquier pestaña/sesion (como Miro/Figma), sin guardar nada en la base
# para algo tan efimero como un color de cursor.
_CURSOR_COLORS = [
    "#f97316", "#22c55e", "#3b82f6", "#ec4899",
    "#a855f7", "#14b8a6", "#eab308", "#ef4444",
]


def _cursor_color(email: str) -> str:
    # Suma de bytes en vez de hash(): hash() de un str varia entre procesos
    # (PYTHONHASHSEED aleatorio por defecto), asi que el mismo email podia
    # terminar con un color distinto despues de reiniciar el backend.
    checksum = sum(email.encode("utf-8"))
    return _CURSOR_COLORS[checksum % len(_CURSOR_COLORS)]


@router.websocket("/{diagram_id}/ws")
async def websocket_endpoint(websocket: WebSocket, diagram_id: str):
    """
    Canal WebSocket por diagrama: broadcast de cambios en tiempo real
    (clases, atributos, metodos, relaciones, progreso del asistente de IA)
    y protocolo de exclusion mutua a nivel de clase.

    Mensajes que puede mandar el cliente:
      {"action": "lock",   "class_id": "..."}
      {"action": "unlock", "class_id": "..."}

    Eventos que puede recibir:
      connected      -> {conn_id}                                (al conectarse, primero que nada)
      locks.snapshot -> {class_id: {email, conn_id}, ...}         (al conectarse)
      class.locked   -> {class_id, email, conn_id}
      class.unlocked -> {class_id}
      lock.denied    -> {class_id, locked_by, locked_by_conn_id}  (solo al que lo pidio)
      cursor.move    -> {conn_id, name, color, x, y, label}       (cursor en vivo de otro colaborador)
      cursor.left    -> {conn_id}                                 (alguien se fue o dejo de mover el mouse)
      presence       -> [{user_id, name, email, color}, ...]      (quienes estan conectados; al entrar/salir alguien)
      chat.message   -> mensaje del chat grupal (ver app/schemas/chat.py), de un colaborador o de la IA
      ai.started / ai.done / ai.error -> progreso de una consulta a la IA, con request_id y requested_by

    Mensajes que puede mandar el cliente para el cursor en vivo:
      {"action": "cursor", "x": <float>, "y": <float>, "label": "<opcional>"}
      {"action": "cursor_left"}   (al salir del lienzo, para borrar el cursor en el resto sin esperar el timeout)

    `x`/`y` viajan en coordenadas del "mundo" del diagrama (la grilla, no
    pixeles de pantalla): cada participante tiene su propio pan/zoom, asi
    que un pixel de pantalla no significa lo mismo para dos personas.

    `conn_id` identifica la CONEXION (no al usuario): dos pestañas de la
    misma persona son dos conn_id distintos. Es lo que el frontend usa para
    saber si el lock es "mio" o "de otro", porque compararlo por email
    fallaba justo en el caso mas obvio -- la misma persona con dos pestañas
    abiertas nunca se bloqueaba a si misma, porque "el lock es de
    ad1@example.com" y esa pestaña TAMBIEN es ad1@example.com. El cursor
    usa el mismo criterio: cada pestaña dibuja su propio puntero local
    y nunca necesita verse a si misma en el broadcast.
    """
    token = websocket.query_params.get("token")
    auth = _authenticate(token, diagram_id)
    if auth is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    email, name, user_id = auth

    conn_id = str(id(websocket))
    await ws_manager.connect(diagram_id, websocket, meta={
        "user_id": user_id, "name": name, "email": email, "color": _cursor_color(email),
    })
    await websocket.send_json({"event": "connected", "data": {"conn_id": conn_id}})
    await websocket.send_json({
        "event": "locks.snapshot",
        "data": lock_manager.snapshot(diagram_id),
    })
    await ws_manager.broadcast(diagram_id, {
        "event": "presence",
        "data": ws_manager.presence(diagram_id),
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue

            action = msg.get("action")

            if action == "cursor":
                x, y = msg.get("x"), msg.get("y")
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    continue
                await ws_manager.broadcast(diagram_id, {
                    "event": "cursor.move",
                    "data": {
                        "conn_id": conn_id,
                        "name": name,
                        "color": _cursor_color(email),
                        "x": x, "y": y,
                        "label": msg.get("label") or None,
                    },
                }, exclude=websocket)
                continue

            if action == "cursor_left":
                await ws_manager.broadcast(diagram_id, {
                    "event": "cursor.left",
                    "data": {"conn_id": conn_id},
                }, exclude=websocket)
                continue

            class_id = msg.get("class_id")
            if not action or not class_id:
                continue

            if action == "lock":
                if lock_manager.acquire(diagram_id, class_id, email, websocket):
                    await ws_manager.broadcast(diagram_id, {
                        "event": "class.locked",
                        "data": {"class_id": class_id, "email": email, "conn_id": conn_id},
                    })
                else:
                    info = lock_manager.info(diagram_id, class_id)
                    await websocket.send_json({
                        "event": "lock.denied",
                        "data": {
                            "class_id": class_id,
                            "locked_by": info.email if info else None,
                            "locked_by_conn_id": str(id(info.ws)) if info else None,
                        },
                    })

            elif action == "unlock":
                if lock_manager.release(diagram_id, class_id, websocket):
                    await ws_manager.broadcast(diagram_id, {
                        "event": "class.unlocked",
                        "data": {"class_id": class_id},
                    })

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(f"[realtime] error en el socket del diagrama {diagram_id}")
    finally:
        ws_manager.disconnect(diagram_id, websocket)
        released = lock_manager.release_all_for(diagram_id, websocket)
        for class_id in released:
            await ws_manager.broadcast(diagram_id, {
                "event": "class.unlocked",
                "data": {"class_id": class_id},
            })
        await ws_manager.broadcast(diagram_id, {
            "event": "cursor.left",
            "data": {"conn_id": conn_id},
        })
        await ws_manager.broadcast(diagram_id, {
            "event": "presence",
            "data": ws_manager.presence(diagram_id),
        })
