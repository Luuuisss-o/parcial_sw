# app/routers/ai.py
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import AiCommandIn, AiCommandAccepted
from app.services.ai_assistant import run_command_background
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
    """Encola un comando en lenguaje natural para editar el diagrama.

    Responde de inmediato: el comando se procesa en segundo plano y tanto el
    progreso (cada clase/atributo creado) como el resultado final viajan por
    el WebSocket del diagrama. Ver app/services/ai_assistant.py.
    """
    diagram = get_my_diagram(db, me, diagram_id)  # valida permisos del usuario
    logger.info(f"[AI COMMAND] diagram_id={diagram_id}, user={me.id}, text={body.text!r}")

    background_tasks.add_task(run_command_background, diagram.id, body.text)
    return AiCommandAccepted(status="processing")
