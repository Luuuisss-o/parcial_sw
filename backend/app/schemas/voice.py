from pydantic import BaseModel


class VoiceTranscribeResult(BaseModel):
    """Resultado de transcribir un audio de voz a texto plano.

    El texto se devuelve para que el frontend lo meta en el mismo flujo que
    un comando escrito a mano (POST /diagrams/{id}/ai/command) -- este
    endpoint solo transcribe, nunca aplica cambios al diagrama.
    """
    text: str
