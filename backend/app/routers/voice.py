# app/routers/voice.py
"""
Transcribe un audio grabado en el navegador a texto plano (dictado por voz
para el asistente del diagrama). Solo transcribe: el texto resultante se
manda desde el frontend como un comando mas a POST /diagrams/{id}/ai/command,
igual que si el usuario lo hubiera escrito a mano.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.voice import VoiceTranscribeResult
from app.services.ai_assistant import describe_error
from app.services.voice_transcribe import transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

_ALLOWED_MIME = {"audio/webm", "audio/ogg", "audio/wav", "audio/mp4", "audio/mpeg"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/transcribe", response_model=VoiceTranscribeResult)
async def transcribe(
    file: UploadFile,
    me: User = Depends(get_current_user),
):
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(400, "El audio tiene que ser WEBM, OGG, WAV o MP4/MP3.")

    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo esta vacio")
    if len(content) > _MAX_BYTES:
        raise HTTPException(400, "El audio es demasiado pesado (máximo 10 MB).")

    try:
        text = transcribe_audio(content, content_type)
    except RuntimeError as e:
        status = 503 if "mucha demanda" in str(e) else 400
        raise HTTPException(status, str(e))
    except Exception as e:
        logger.error(f"[voice] fallo transcribiendo audio: {type(e).__name__}: {e}")
        raise HTTPException(502, describe_error(e))

    if not text:
        raise HTTPException(422, "No se entendió nada en el audio. Probá grabar de nuevo, más cerca del micrófono.")

    return VoiceTranscribeResult(text=text)
