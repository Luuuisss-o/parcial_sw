# app/services/voice_transcribe.py
"""
Transcribe un audio grabado en el navegador (dictado por voz para el
asistente del diagrama) a texto plano, usando Gemini.

Reemplaza la Web Speech API del navegador (window.SpeechRecognition), que
depende de que el usuario use Chrome/Edge y de que el propio navegador
tenga conexion directa a los servidores de reconocimiento de voz de
Google -- en la practica falla seguido y sin un motivo claro para el
usuario. Acá el audio se manda como bytes al backend, que ya tiene la
GEMINI_API_KEY configurada, y el texto que vuelve entra al mismo flujo que
un comando escrito a mano (POST /diagrams/{id}/ai/command). Este servicio
NO interpreta el comando ni toca el diagrama: solo transcribe.
"""
from __future__ import annotations

import logging
import time

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"
REQUEST_TIMEOUT = 45.0

SYSTEM_PROMPT = """Transcribí exactamente lo que se dice en este audio, en \
español. Devolvé ÚNICAMENTE el texto transcripto, sin comillas, sin \
comentarios, sin traducir ni corregir el sentido de lo que se dijo. Si no \
se entiende nada o el audio está en silencio, devolvé un string vacío."""


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no esta configurada en el backend (.env).")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def call(model: str):
        return client.models.generate_content(
            model=model,
            contents=[
                SYSTEM_PROMPT,
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT * 1000)),
            ),
        )

    def is_unavailable(e: Exception) -> bool:
        return (
            "UNAVAILABLE" in str(e)
            or "503" in str(e)
            or "DEADLINE_EXCEEDED" in str(e)
            or "504" in str(e)
        )

    # Mismo patron de reintentos que diagram_vision.py: la capa gratuita de
    # Gemini devuelve 503 "high demand" seguido y suele ser transitorio.
    response = None
    last_error: Exception | None = None
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = call(MODEL)
            break
        except Exception as e:
            last_error = e
            if not is_unavailable(e):
                raise
            if attempt == max_attempts - 1:
                break
            wait_s = 2 * (attempt + 1)
            logger.warning(f"[voice] intento {attempt + 1} con {MODEL} fallo (503), reintentando en {wait_s}s...")
            time.sleep(wait_s)

    if response is None:
        if last_error is not None and is_unavailable(last_error):
            logger.warning(f"[voice] {MODEL} saturado, probando fallback {FALLBACK_MODEL}...")
            try:
                response = call(FALLBACK_MODEL)
            except Exception as e:
                if is_unavailable(e):
                    raise RuntimeError(
                        "El servicio de IA está con mucha demanda en este momento. Probá de nuevo en un minuto."
                    ) from e
                raise
        else:
            raise last_error

    return (response.text or "").strip()
