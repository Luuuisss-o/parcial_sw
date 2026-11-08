# app/routers/ai.py
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import AiCommandIn, AiCommandAccepted, AiSettingsIn, AiSettingsOut
from app.services import chat_service
from app.utils import realtime_events
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


@router.get("/{diagram_id}/ai/settings", response_model=AiSettingsOut)
def get_ai_settings(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Configuracion de la IA en este diagrama (cualquier integrante la ve)."""
    diagram = get_my_diagram(db, me, diagram_id)
    return AiSettingsOut(solutions_enabled=diagram.ai_solutions_enabled)


@router.patch("/{diagram_id}/ai/settings", response_model=AiSettingsOut)
async def update_ai_settings(
    diagram_id: UUID,
    body: AiSettingsIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Habilita o deshabilita que la IA entregue soluciones de diseño
    completas cuando se las piden. Solo el dueño del diagrama.

    El cambio se avisa por WebSocket (`ai.settings`) a todos los conectados,
    para que cada integrante vea en su chat como esta configurada la IA."""
    diagram = get_my_diagram(db, me, diagram_id)
    if diagram.owner_id != me.id:
        raise HTTPException(403, "Solo el dueño del diagrama puede configurar la IA")
    diagram.ai_solutions_enabled = body.solutions_enabled
    db.commit()
    logger.info(f"[AI SETTINGS] diagram={diagram.id} solutions_enabled={body.solutions_enabled} by={me.id}")
    realtime_events.fire(realtime_events.notify_ai_settings(
        diagram.id, {"solutions_enabled": body.solutions_enabled, "changed_by": me.name},
    ))
    return AiSettingsOut(solutions_enabled=diagram.ai_solutions_enabled)
