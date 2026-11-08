# app/services/chat_service.py
"""
Logica del chat grupal del diagrama y de las consultas publicas a la IA.

Flujo de una consulta a la IA (CU-15 / CU-16):

  1. Un colaborador escribe en el chat "@IA ..." (o usa el boton de la IA).
  2. Se guarda su mensaje como pregunta (asks_ai=True) y se difunde por
     WebSocket a TODOS los conectados -> la pregunta es publica.
  3. En segundo plano se llama al modelo indicandole QUIEN pregunta (nombre +
     email) y el historial de consultas previas de esa misma persona.
  4. La respuesta se guarda dirigida a ese usuario (addressed_to_*) y se
     difunde tambien a todos -> la respuesta es publica.

Asi cada consulta queda atribuida a su autor aunque varios usuarios le
pregunten a la IA al mismo tiempo: cada pregunta tiene su propio id
(request_id) y la respuesta referencia ese id (reply_to_id).
"""
from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.chat import ChatMessage, ChatRole
from app.models.uml import Diagram
from app.models.user import User
from app.schemas.chat import ChatMessageOut
from app.services import ai_assistant
from app.utils import realtime_events

logger = logging.getLogger(__name__)

AI_DISPLAY_NAME = "Asistente IA"

# "@IA", "@ia", "@AI" o "@asistente" como palabra suelta en cualquier parte del
# mensaje. No matchea dentro de un email ("x@ia.com" no es una mencion: antes
# del @ hay una letra) ni "@iaxyz".
_AI_MENTION_RE = re.compile(r"(?<![\w@.])@(?:ia|ai|asistente)\b[,:]?", re.IGNORECASE)

# Cuantas consultas previas del mismo usuario se le pasan al modelo.
USER_HISTORY_TURNS = 6

# Memoria hibrida: cuantos mensajes recientes del chat del equipo (de todos)
# se le pasan al modelo como contexto global, y cuanto texto por mensaje.
TEAM_CONTEXT_MESSAGES = 12
TEAM_CONTEXT_MAX_CHARS = 400


def parse_ai_mention(text: str, ask_ai_flag: bool = False) -> tuple[bool, str]:
    """Devuelve (es_consulta_a_la_ia, texto_sin_la_mencion)."""
    mentioned = bool(_AI_MENTION_RE.search(text))
    clean = _AI_MENTION_RE.sub(" ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    asks = ask_ai_flag or mentioned
    # "@IA" solo, sin pregunta: no hay nada que mandarle al modelo.
    if asks and not clean:
        return False, text.strip()
    return asks, (clean if asks else text.strip())


def question_text(content: str) -> str:
    """Texto de una pregunta guardada, sin la mencion "@IA", para el modelo."""
    return parse_ai_mention(content, True)[1]


def to_payload(msg: ChatMessage) -> dict:
    """Serializa un mensaje igual que el endpoint REST (para el WebSocket)."""
    return ChatMessageOut.model_validate(msg).model_dump(mode="json")


def create_user_message(db: Session, diagram: Diagram, author: User, text: str, asks_ai: bool) -> ChatMessage:
    msg = ChatMessage(
        diagram_id=diagram.id,
        role=ChatRole.USER,
        author_id=author.id,
        author_name=author.name,
        author_email=author.email,
        content=text,
        asks_ai=asks_ai,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def publish(diagram_id: UUID, msg: ChatMessage) -> None:
    realtime_events.fire(realtime_events.notify_chat_message(diagram_id, to_payload(msg)))


def user_ai_history(db: Session, diagram_id: UUID, user_id: int, before_seq: int,
                    limit: int = USER_HISTORY_TURNS) -> list[tuple[str, str]]:
    """Pares (pregunta, respuesta) que ESTE usuario ya le hizo a la IA en este
    diagrama, del mas viejo al mas nuevo. Solo los suyos: la IA no debe
    mezclar el hilo de un colaborador con el de otro."""
    preguntas = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.diagram_id == diagram_id,
            ChatMessage.author_id == user_id,
            ChatMessage.asks_ai.is_(True),
            ChatMessage.seq < before_seq,
        )
        .order_by(ChatMessage.seq.desc())
        .limit(limit)
        .all()
    )
    if not preguntas:
        return []
    ids = [p.id for p in preguntas]
    respuestas = {
        r.reply_to_id: r.content
        for r in db.query(ChatMessage).filter(
            ChatMessage.reply_to_id.in_(ids),
            ChatMessage.role == ChatRole.ASSISTANT,
        )
    }
    pares = [(question_text(p.content), respuestas[p.id]) for p in reversed(preguntas) if p.id in respuestas]
    return pares


def team_context(db: Session, diagram_id: UUID, before_seq: int, exclude_user_id: int | None,
                 limit: int = TEAM_CONTEXT_MESSAGES) -> list[ai_assistant.TeamMessage]:
    """Conversacion reciente de TODO el equipo (contexto global de la memoria
    hibrida), anterior a la pregunta actual, de la mas vieja a la mas nueva.

    Se excluye el ida y vuelta de quien pregunta con la IA (sus preguntas
    "@IA" y las respuestas dirigidas a el): eso ya viaja en su hilo
    individual, y repetirlo solo gasta tokens y confunde los dos niveles.
    Sus mensajes normales al equipo si se incluyen. Los errores del
    asistente no aportan contexto y se omiten."""
    rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.diagram_id == diagram_id,
            ChatMessage.seq < before_seq,
            ChatMessage.role != ChatRole.ERROR,
        )
        .order_by(ChatMessage.seq.desc())
        .limit(limit * 3)  # margen por los que se descartan abajo
        .all()
    )
    out: list[ai_assistant.TeamMessage] = []
    for m in rows:
        if exclude_user_id is not None and (
            (m.role == ChatRole.USER and m.asks_ai and m.author_id == exclude_user_id)
            or (m.role == ChatRole.ASSISTANT and m.addressed_to_id == exclude_user_id)
        ):
            continue
        text = question_text(m.content) if m.asks_ai else m.content
        if len(text) > TEAM_CONTEXT_MAX_CHARS:
            text = text[:TEAM_CONTEXT_MAX_CHARS].rstrip() + "…"
        out.append(ai_assistant.TeamMessage(
            author=m.author_name,
            content=(f"(le pregunto a la IA) {text}" if m.asks_ai else text),
            is_ai=m.role == ChatRole.ASSISTANT,
            addressed_to=m.addressed_to_name,
        ))
        if len(out) >= limit:
            break
    return list(reversed(out))


def address_reply(reply: str, name: str) -> str:
    """Garantiza que la respuesta nombre a quien pregunto.

    El prompt ya le pide al modelo que lo haga, pero un LLM no es
    determinista: si la respuesta no menciona a la persona (por nombre o
    primer nombre), se antepone el nombre para que en el chat grupal quede
    siempre claro a quien le esta hablando la IA."""
    reply = (reply or "").strip()
    if not name:
        return reply
    first = name.split()[0]
    if first.lower() in reply.lower():
        return reply
    if not reply:
        return f"{name}: (sin respuesta)"
    # No se pasa a minuscula la primera letra: podria ser un nombre de clase.
    return f"{first}, {reply}"


def _save_ai_message(db: Session, question: ChatMessage, role: ChatRole, content: str,
                     actions: list | None = None, ai_mode: str | None = None) -> ChatMessage:
    msg = ChatMessage(
        diagram_id=question.diagram_id,
        role=role,
        author_id=None,
        author_name=AI_DISPLAY_NAME,
        author_email=None,
        content=content,
        asks_ai=False,
        reply_to_id=question.id,
        addressed_to_id=question.author_id,
        addressed_to_name=question.author_name,
        actions=actions or None,
        ai_mode=ai_mode,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def run_ai_question_background(question_id: UUID) -> None:
    """Responde una pregunta del chat con la IA y publica el resultado.

    Corre como BackgroundTask (fuera del request), con su propia sesion de BD.
    """
    db = SessionLocal()
    try:
        question = db.get(ChatMessage, question_id)
        if question is None:
            logger.warning(f"[AI CHAT] la pregunta {question_id} ya no existe")
            return
        diagram = db.get(Diagram, question.diagram_id)
        if diagram is None:
            logger.warning(f"[AI CHAT] el diagrama {question.diagram_id} ya no existe")
            return

        requester = ai_assistant.Requester(
            user_id=question.author_id,
            name=question.author_name,
            email=question.author_email,
        )
        requested_by = {"id": requester.user_id, "name": requester.name}
        request_id = str(question.id)

        realtime_events.fire(realtime_events.notify_ai_started(
            diagram.id, question_text(question.content), request_id=request_id, requested_by=requested_by,
        ))

        history = (
            user_ai_history(db, diagram.id, question.author_id, question.seq)
            if question.author_id is not None else []
        )

        try:
            team = team_context(db, diagram.id, question.seq, exclude_user_id=question.author_id)
            result = ai_assistant.run_command(
                db, diagram, question_text(question.content), requester=requester,
                history=history, team_context=team,
            )
            reply = address_reply(result.reply, requester.name)
            answer = _save_ai_message(
                db, question, ChatRole.ASSISTANT, reply, result.actions, ai_mode=result.mode,
            )
            publish(diagram.id, answer)
            realtime_events.fire(realtime_events.notify_ai_done(
                diagram.id, reply, result.actions,
                request_id=request_id, requested_by=requested_by, message_id=str(answer.id),
            ))
        except Exception as e:
            logger.error(f"[AI CHAT] fallo: {type(e).__name__}: {e}")
            db.rollback()
            detail = address_reply(ai_assistant.describe_error(e), requester.name)
            err = _save_ai_message(db, question, ChatRole.ERROR, detail)
            publish(diagram.id, err)
            realtime_events.fire(realtime_events.notify_ai_error(
                diagram.id, detail, request_id=request_id, requested_by=requested_by,
            ))
    finally:
        db.close()
