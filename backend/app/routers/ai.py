# app/routers/ai.py
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import AiCommandIn, AiCommandAccepted, AiSettingsIn, AiSettingsOut, AiTestOut
from app.services import chat_service, llm_providers
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


def _settings_out(diagram) -> AiSettingsOut:
    cfg = llm_providers.config_for(diagram)
    return AiSettingsOut(
        solutions_enabled=diagram.ai_solutions_enabled,
        provider=cfg.kind,
        provider_is_default=not diagram.ai_provider,
        model=cfg.model or (llm_providers.DEFAULT_GEMINI_MODEL if cfg.kind == llm_providers.PROVIDER_GEMINI else None),
        base_url=cfg.base_url,
        has_api_key=bool(diagram.ai_api_key),
        provider_label=cfg.label,
    )


def _owned(db, me, diagram_id):
    diagram = get_my_diagram(db, me, diagram_id)
    if diagram.owner_id != me.id:
        raise HTTPException(403, "Solo el dueño del diagrama puede configurar la IA")
    return diagram


@router.get("/{diagram_id}/ai/settings", response_model=AiSettingsOut)
def get_ai_settings(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Configuracion de la IA en este diagrama (cualquier integrante la ve)."""
    return _settings_out(get_my_diagram(db, me, diagram_id))


@router.patch("/{diagram_id}/ai/settings", response_model=AiSettingsOut)
async def update_ai_settings(
    diagram_id: UUID,
    body: AiSettingsIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Cambia la configuracion de la IA del diagrama. Solo el dueño.

    - solutions_enabled (CU-18): si la IA puede entregar soluciones completas.
    - provider/base_url/model/api_key (CU-17): que modelo responde. Con
      "openai_compatible" se usa un modelo local o en Colab (Ollama,
      LM Studio, vLLM...) en base_url.

    El cambio se avisa por WebSocket (`ai.settings`) a todos los conectados."""
    diagram = _owned(db, me, diagram_id)
    if body.solutions_enabled is not None:
        diagram.ai_solutions_enabled = body.solutions_enabled
    if body.provider is not None:
        if body.provider == "default":
            diagram.ai_provider = diagram.ai_base_url = diagram.ai_model = diagram.ai_api_key = None
        else:
            diagram.ai_provider = body.provider
    if body.provider != "default":
        if body.base_url is not None:
            diagram.ai_base_url = body.base_url or None
        if body.model is not None:
            diagram.ai_model = body.model.strip() or None
        if body.api_key is not None:
            diagram.ai_api_key = body.api_key.strip() or None
    if diagram.ai_provider == llm_providers.PROVIDER_OPENAI and not (diagram.ai_base_url and diagram.ai_model):
        db.rollback()
        raise HTTPException(422, "Para un modelo local/OpenAI-compatible hay que indicar el endpoint y el modelo")
    db.commit()
    out = _settings_out(diagram)
    logger.info(f"[AI SETTINGS] diagram={diagram.id} by={me.id} -> {out.provider_label} solutions={out.solutions_enabled}")
    realtime_events.fire(realtime_events.notify_ai_settings(
        diagram.id, {**out.model_dump(), "changed_by": me.name},
    ))
    return out


@router.post("/{diagram_id}/ai/settings/test", response_model=AiTestOut)
def test_ai_settings(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Prueba el proveedor configurado con una consulta minima (solo el dueño)."""
    diagram = _owned(db, me, diagram_id)
    cfg = llm_providers.config_for(diagram)
    try:
        reply = llm_providers.test_connection(cfg)
        return AiTestOut(ok=True, provider_label=cfg.label, detail=f"Respondió: «{reply}»")
    except Exception as e:
        from app.services.ai_assistant import describe_error
        return AiTestOut(ok=False, provider_label=cfg.label, detail=describe_error(e))
