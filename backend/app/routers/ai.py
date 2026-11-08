# app/routers/ai.py
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import AiCommandIn, AiCommandAccepted
from app.services import chat_service
from ._helpers import get_my_diagram

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagrams", tags=["ai"])


@router.post(
    "/{diagram_id}/ai/command",
    response_model=AiCommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def ai_command(
    diagram_id: UUID,
    body: AiCommandIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Encola una consulta/comando en lenguaje natural para la IA.

    Desde la Fase 2 toda consulta a la IA es publica: se registra como una
    pregunta en el chat grupal del diagrama (igual que escribir "@IA ..." en
    POST /diagrams/{id}/chat) y la respuesta llega como mensaje del chat
    dirigido a quien pregunto, visible para todos los colaboradores.

    Responde de inmediato: el progreso (cada clase/atributo creado) y el
    resultado final viajan por el WebSocket del diagrama.
    """
    diagram = get_my_diagram(db, me, diagram_id)  # valida permisos del usuario
    logger.info(f"[AI COMMAND] diagram_id={diagram_id}, user={me.id}, text={body.text!r}")

    question = chat_service.create_user_message(db, diagram, me, body.text.strip(), asks_ai=True)
    chat_service.publish(diagram.id, question)
    background_tasks.add_task(chat_service.run_ai_question_background, question.id)
    return AiCommandAccepted(status="processing", request_id=question.id)
