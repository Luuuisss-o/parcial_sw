# app/routers/chat.py
"""
Chat grupal del diagrama (CU-14) y consultas publicas a la IA (CU-15/CU-16).

  GET  /diagrams/{id}/chat?limit=50&before_seq=N   historial (mas viejos primero)
  POST /diagrams/{id}/chat   {"text": "...", "ask_ai": false}

Todo mensaje nuevo se difunde por el WebSocket del diagrama como
`chat.message` a todos los conectados. Si el texto menciona a la IA
("@IA ...") o viene con ask_ai=true, ademas se encola la consulta: la
respuesta llega despues como otro `chat.message` (role=ASSISTANT) dirigido
al autor de la pregunta, visible para todo el equipo.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models.chat import ChatMessage, ChatRole
from app.models.user import User
from app.schemas.chat import AiContextOut, ChatHistoryOut, ChatMessageIn, ChatMessageOut, DeviceAnswerIn
from app.services import chat_service
from app.utils import realtime_events

from ._helpers import get_my_diagram

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagrams", tags=["chat"])


@router.get("/{diagram_id}/chat", response_model=ChatHistoryOut)
def list_chat(
    diagram_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before_seq: Optional[int] = Query(None, description="Paginar hacia atras: mensajes anteriores a este seq"),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    diagram = get_my_diagram(db, me, diagram_id)
    q = db.query(ChatMessage).filter(ChatMessage.diagram_id == diagram.id)
    if before_seq is not None:
        q = q.filter(ChatMessage.seq < before_seq)
    rows = q.order_by(ChatMessage.seq.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = list(reversed(rows[:limit]))
    return ChatHistoryOut(items=rows, has_more=has_more)


@router.post("/{diagram_id}/chat", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
def post_chat(
    diagram_id: UUID,
    body: ChatMessageIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    diagram = get_my_diagram(db, me, diagram_id)
    asks_ai, _ = chat_service.parse_ai_mention(body.text, body.ask_ai)
    # Se guarda el texto tal como lo escribio el usuario (con su "@IA"), asi el
    # chat muestra exactamente lo que mando; al modelo le llega sin la mencion.
    msg = chat_service.create_user_message(db, diagram, me, body.text, asks_ai)
    chat_service.publish(diagram.id, msg)
    logger.info(f"[CHAT] diagram={diagram.id} user={me.id} asks_ai={asks_ai}")

    if asks_ai and body.answer_on_device:
        # La responde el modelo local del celular de quien pregunta: el
        # servidor no llama a ningun modelo, solo avisa a todos que la IA
        # (en ese celular) esta respondiendo.
        realtime_events.fire(realtime_events.notify_ai_started(
            diagram.id, chat_service.question_text(msg.content), request_id=str(msg.id),
            requested_by={"id": me.id, "name": me.name}, on_device=True,
        ))
    elif asks_ai:
        background_tasks.add_task(chat_service.run_ai_question_background, msg.id)
    return msg


def _my_pending_question(db: Session, me: User, diagram_id: UUID, question_id: UUID) -> tuple[ChatMessage, object]:
    diagram = get_my_diagram(db, me, diagram_id)
    q = db.get(ChatMessage, question_id)
    if q is None or q.diagram_id != diagram.id or not q.asks_ai or q.role != ChatRole.USER:
        raise HTTPException(404, "Consulta no encontrada")
    if q.author_id != me.id:
        raise HTTPException(403, "Solo quien hizo la consulta puede responderla con su modelo local")
    return q, diagram


@router.get("/{diagram_id}/chat/{question_id}/context", response_model=AiContextOut)
def question_context(
    diagram_id: UUID,
    question_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Contexto (memoria hibrida + estado del diagrama) para que el modelo
    local del celular responda la consulta. Solo para su autor."""
    q, diagram = _my_pending_question(db, me, diagram_id, question_id)
    return chat_service.device_context(db, q, diagram)


@router.post("/{diagram_id}/chat/{question_id}/answer", response_model=ChatMessageOut,
             status_code=status.HTTP_201_CREATED)
def answer_from_device(
    diagram_id: UUID,
    question_id: UUID,
    body: DeviceAnswerIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Publica la respuesta que generó el modelo local del celular. Queda en
    el chat dirigida al autor y visible para todo el equipo, igual que una
    respuesta del servidor. Las ediciones que haya hecho el celular ya se
    aplicaron por la API REST normal (y se difundieron por WebSocket)."""
    q, _ = _my_pending_question(db, me, diagram_id, question_id)
    already = db.query(ChatMessage).filter(ChatMessage.reply_to_id == q.id).first()
    if already is not None:
        raise HTTPException(409, "Esa consulta ya tiene respuesta")
    return chat_service.save_device_answer(
        db, q, content=body.content, error=body.error, actions=body.actions,
        ai_mode=body.ai_mode, model_label=body.model_label,
    )
