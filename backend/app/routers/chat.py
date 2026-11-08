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

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatHistoryOut, ChatMessageIn, ChatMessageOut
from app.services import chat_service

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

    if asks_ai:
        background_tasks.add_task(chat_service.run_ai_question_background, msg.id)
    return msg
