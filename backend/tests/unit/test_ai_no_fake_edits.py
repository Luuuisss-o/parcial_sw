"""El asistente del servidor nunca debe confirmar ediciones que no hizo.

Caso real (Gemini): ante "@IA crea la clase cliente con nombre y email"
contesto sin herramientas, se le insistio y respondio "tenes razon, ahi
ejecuto las herramientas..." otra vez sin ejecutar nada, y ese texto se
publico en el chat. Se simula el modelo con una sesion falsa.
"""
from __future__ import annotations

import pytest

from app.services import ai_assistant, llm_providers
from app.services.llm_providers import ToolCall, Turn


class FakeExecutor:
    def __init__(self, db, diagram):
        self.created = []

    def snapshot(self):
        return {"classes": [], "relations": []}

    def create_class(self, name, **kw):
        self.created.append(name)
        return {"id": "c1", "name": name}


class FakeSession:
    """Devuelve los turnos de `script` en orden, sea cual sea el metodo."""

    def __init__(self, script):
        self.script = script

    def _next(self):
        return self.script.pop(0) if self.script else Turn(text="")

    def start(self, system, prompt, tools):
        return self._next()

    def insist_on_tools(self, message):
        return self._next()

    def send_tool_results(self, results):
        return self._next()


@pytest.fixture
def run(monkeypatch):
    def _run(*sessions):
        queue = list(sessions)
        monkeypatch.setattr(llm_providers, "open_session", lambda cfg: queue.pop(0))
        monkeypatch.setattr(ai_assistant, "DiagramToolExecutor", FakeExecutor)
        cfg = llm_providers.ProviderConfig(model="fake")
        return ai_assistant._run(None, object(), "@IA crea la clase Cliente con nombre y email",
                                 None, None, None, ai_assistant.MODE_AUTO, False, cfg)
    return _run


PROMESA = Turn(text="Tenes razon, mil disculpas. Ahi mismo ejecuto las herramientas.")


def test_promete_sin_ejecutar_nunca_se_publica(run):
    res = run(FakeSession([PROMESA, PROMESA]), FakeSession([PROMESA]))
    assert res.actions == []
    assert res.reply == ai_assistant.NO_CHANGES_REPLY


def test_reintento_en_sesion_limpia_ejecuta(run):
    call = ToolCall("1", "create_class", {"name": "Cliente"})
    res = run(
        FakeSession([PROMESA, PROMESA]),
        FakeSession([Turn(calls=[call]), Turn(text="Creé la clase Cliente.")]),
    )
    assert [a["tool"] for a in res.actions] == ["create_class"]
    assert res.reply == "Creé la clase Cliente."


def test_si_insistir_alcanza_no_se_reintenta(run):
    call = ToolCall("1", "create_class", {"name": "Cliente"})
    res = run(FakeSession([PROMESA, Turn(calls=[call]), Turn(text="Listo: Cliente creada.")]))
    assert len(res.actions) == 1
    assert res.reply == "Listo: Cliente creada."
