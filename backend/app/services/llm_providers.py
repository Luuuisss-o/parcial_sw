# app/services/llm_providers.py
"""
Proveedores de IA intercambiables (Fase 2, CU-17).

El asistente (ai_assistant.run_command) no habla directo con un SDK: usa una
"sesion" con dos operaciones, empezar y continuar con los resultados de las
herramientas. Asi el mismo loop (herramientas, modo mentor, memoria hibrida,
entrega de soluciones) funciona con cualquier proveedor:

  - "gemini": Google AI Studio / Gemini (API de interactions del SDK
    google-genai). Es el proveedor por defecto.
  - "openai_compatible": cualquier servidor con la API "chat completions" de
    OpenAI. Es el estandar que exponen los modelos LOCALES:
        Ollama     -> http://localhost:11434/v1
        LM Studio  -> http://localhost:1234/v1
        vLLM / llama.cpp server en Google Colab (expuesto con ngrok o
        cloudflared) -> https://<tunel>/v1
    y tambien proveedores en la nube (OpenAI, Groq, el endpoint compatible
    de Gemini...).

Cual se usa lo decide, por diagrama, su dueño (PATCH /diagrams/{id}/ai/settings);
si el diagrama no define nada se usa el proveedor por defecto del servidor
(variables AI_PROVIDER / AI_BASE_URL / AI_MODEL / AI_API_KEY del .env, o
Gemini con GEMINI_API_KEY).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
from google import genai

from app.core.config import settings

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai_compatible"
PROVIDERS = (PROVIDER_GEMINI, PROVIDER_OPENAI)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
REQUEST_TIMEOUT = 45.0
# Un modelo local en una PC sin GPU (o en Colab gratis) puede tardar bastante
# mas que una API en la nube en generar la respuesta.
LOCAL_REQUEST_TIMEOUT = 180.0


class ProviderError(RuntimeError):
    """Error con un mensaje ya listo para mostrarle al usuario en el chat."""


@dataclass
class ProviderConfig:
    kind: str = PROVIDER_GEMINI
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None

    @property
    def label(self) -> str:
        if self.kind == PROVIDER_GEMINI:
            return f"Gemini ({self.model or DEFAULT_GEMINI_MODEL})"
        host = urlparse(self.base_url or "").hostname or self.base_url
        return f"{self.model} ({host})"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Turn:
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)


def server_default() -> ProviderConfig:
    """Proveedor por defecto del servidor (.env)."""
    kind = (settings.AI_PROVIDER or PROVIDER_GEMINI).strip()
    if kind == PROVIDER_OPENAI:
        return ProviderConfig(kind, settings.AI_MODEL or None, settings.AI_BASE_URL or None,
                              settings.AI_API_KEY or None)
    return ProviderConfig(PROVIDER_GEMINI, settings.AI_MODEL or None, None, None)


def config_for(diagram) -> ProviderConfig:
    """Proveedor que corresponde a un diagrama: el que configuro su dueño, o
    el por defecto del servidor."""
    kind = getattr(diagram, "ai_provider", None)
    if not kind:
        return server_default()
    return ProviderConfig(kind, diagram.ai_model or None, diagram.ai_base_url or None,
                          diagram.ai_api_key or None)


def open_session(cfg: ProviderConfig):
    if cfg.kind == PROVIDER_OPENAI:
        return OpenAICompatibleSession(cfg)
    return GeminiSession(cfg)


# ---------------------------------------------------------------------------
# Gemini (google-genai, API de interactions)
# ---------------------------------------------------------------------------
class GeminiSession:
    def __init__(self, cfg: ProviderConfig):
        key = cfg.api_key or settings.GEMINI_API_KEY
        if not key:
            raise ProviderError("GEMINI_API_KEY no esta configurada en el backend (.env).")
        self.model = cfg.model or DEFAULT_GEMINI_MODEL
        self.client = genai.Client(api_key=key)
        self._system = ""
        self._tools = None
        self._last_id = None

    @staticmethod
    def _turn(interaction) -> Turn:
        calls = [
            ToolCall(s.id, s.name, dict(s.arguments or {}))
            for s in interaction.steps if s.type == "function_call"
        ]
        return Turn(text=interaction.output_text or "", calls=calls)

    def start(self, system: str, prompt: str, tools: list | None) -> Turn:
        from app.services.ai_tools import TOOLS
        self._system = system
        self._tools = TOOLS if tools is not None else None
        kwargs = dict(model=self.model, input=prompt, system_instruction=system)
        if self._tools:
            kwargs["tools"] = self._tools
        it = self.client.interactions.create(timeout=REQUEST_TIMEOUT, **kwargs)
        self._last_id = it.id
        return self._turn(it)

    def insist_on_tools(self, message: str) -> Turn:
        """El modelo respondio sin usar herramientas cuando el pedido era una
        edicion: se le avisa y se le pide que las use."""
        it = self.client.interactions.create(
            timeout=REQUEST_TIMEOUT, model=self.model, input=message,
            system_instruction=self._system, tools=self._tools, previous_interaction_id=self._last_id,
        )
        self._last_id = it.id
        return self._turn(it)

    def send_tool_results(self, results: list[tuple[ToolCall, str]]) -> Turn:
        # system_instruction se reenvia en cada vuelta: sin esto la respuesta
        # final (tras ejecutar herramientas) ignoraba las reglas del prompt.
        it = self.client.interactions.create(
            timeout=REQUEST_TIMEOUT,
            model=self.model,
            input=[
                {"type": "function_result", "name": c.name, "call_id": c.id,
                 "result": [{"type": "text", "text": payload}]}
                for c, payload in results
            ],
            system_instruction=self._system,
            tools=self._tools,
            previous_interaction_id=self._last_id,
        )
        self._last_id = it.id
        return self._turn(it)


# ---------------------------------------------------------------------------
# OpenAI-compatible (Ollama, LM Studio, vLLM / llama.cpp en Colab, ...)
# ---------------------------------------------------------------------------
class OpenAICompatibleSession:
    def __init__(self, cfg: ProviderConfig):
        if not cfg.base_url or not cfg.model:
            raise ProviderError("El proveedor de IA local no tiene configurados el endpoint y el modelo.")
        self.cfg = cfg
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"
        self.messages: list[dict[str, Any]] = []
        self.tools: list | None = None
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        self.http = httpx.Client(headers=headers, timeout=LOCAL_REQUEST_TIMEOUT)

    def _post(self, tool_choice: str | None = None) -> Turn:
        body: dict[str, Any] = {"model": self.cfg.model, "messages": self.messages, "temperature": 0.2}
        if self.tools:
            body["tools"] = self.tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        try:
            r = self.http.post(self.url, json=body)
        except httpx.TimeoutException:
            raise ProviderError(f"El modelo {self.cfg.model} tardó demasiado en responder ({self.cfg.base_url}).")
        except httpx.HTTPError as e:
            raise ProviderError(
                f"No se pudo conectar con el servidor de IA configurado ({self.cfg.base_url}). "
                f"¿Está encendido (Ollama / LM Studio / Colab)? Detalle: {type(e).__name__}"
            )
        if r.status_code in (401, 403):
            raise ProviderError("El servidor de IA configurado rechazó el token. Revisá la configuración de la IA.")
        if r.status_code == 404:
            raise ProviderError(
                f"El servidor de IA no encontró el modelo «{self.cfg.model}» o la ruta {self.url}. "
                f"Revisá el nombre del modelo y que el endpoint termine en /v1."
            )
        if r.status_code >= 400:
            raise ProviderError(f"El servidor de IA respondió con error {r.status_code}: {r.text[:200]}")
        try:
            msg = r.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError):
            raise ProviderError("El servidor de IA devolvió una respuesta que no es formato OpenAI.")

        # Se guarda el mensaje del asistente tal cual para la proxima vuelta.
        self.messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except ValueError:
                    args = {}
            calls.append(ToolCall(tc.get("id") or f"call_{i}", fn.get("name", ""), args))
        return Turn(text=msg.get("content") or "", calls=calls)

    def start(self, system: str, prompt: str, tools: list | None) -> Turn:
        from app.services.ai_tools import OPENAI_TOOLS
        self.tools = OPENAI_TOOLS if tools is not None else None
        self.messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        return self._post()

    def insist_on_tools(self, message: str) -> Turn:
        self.messages.append({"role": "user", "content": message})
        # "required": el servidor obliga al modelo a llamar al menos una tool
        # (Ollama, vLLM, LM Studio y OpenAI lo soportan).
        return self._post(tool_choice="required")

    def send_tool_results(self, results: list[tuple[ToolCall, str]]) -> Turn:
        for c, payload in results:
            self.messages.append({"role": "tool", "tool_call_id": c.id, "name": c.name, "content": payload})
        return self._post()


def test_connection(cfg: ProviderConfig) -> str:
    """Prueba rapida del proveedor (boton "Probar conexión" del frontend)."""
    s = open_session(cfg)
    turn = s.start("Respondé en una sola palabra.", "Decí: ok", tools=None)
    return (turn.text or "").strip()[:80]
