"""
Modelo PROPIO del equipo en el servidor: Gemma 3 1B ajustado con LoRA
(training/), servido con llama.cpp en una instancia aparte (deploy/model_server).

A diferencia de Gemini, este modelo no hace "tool calling": se entreno para
responder un JSON {"say": ..., "actions": [...]} con un prompt exacto. Por eso
aca se usa EL MISMO contrato del entrenamiento (training/prompt_contract.py,
que lee el prompt de sistema de mobile/lib/services/assistant_prompt.dart):
si el prompt difiriera en una coma, el modelo perderia lo aprendido.

Con la respuesta:
  - consulta de edicion (modo AUTO): las acciones se ejecutan por el mismo
    servicio de operaciones (con la regla de confirmacion de eliminaciones);
  - consulta del asesor (modo MENTOR): las acciones NO se ejecutan; si el
    diagrama permite propuestas se validan y quedan como propuesta.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path

import httpx

from app.core.config import settings
from app.services import ai_proposals
from app.services.ai_tools import CONFIRM_RE, DiagramToolExecutor, ToolError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 240.0  # CPU de 2 nucleos: una respuesta tarda ~20-60 s
MAX_ACTIONS = 40
PROPOSAL_NOT_APPLIED_NOTE = ("\n\n_(Todavía no se aplicó nada: quedó como **propuesta** para que "
                             "quien preguntó o el dueño la revise y la aplique.)_")


# ---------------------------------------------------------------------------
# Contrato del entrenamiento (una sola fuente: training/prompt_contract.py)
# ---------------------------------------------------------------------------
def _contract_path() -> Path:
    env = os.environ.get("PROMPT_CONTRACT_PATH")
    candidates = [Path(env)] if env else []
    here = Path(__file__).resolve()
    candidates += [
        Path("/app/training/prompt_contract.py"),            # imagen Docker
        here.parents[3] / "training" / "prompt_contract.py",  # repo (desarrollo)
    ]
    for p in candidates:
        if p.exists():
            return p
    raise RuntimeError("No encontré training/prompt_contract.py (contrato del modelo propio)")


_contract = None


def contract():
    global _contract
    if _contract is None:
        spec = importlib.util.spec_from_file_location("prompt_contract", _contract_path())
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _contract = mod
    return _contract


def build_prompt(ctx: dict) -> str:
    c = contract()
    return c.gemma_chat(c.system_prompt(), c.build_user_message(ctx))


# ---------------------------------------------------------------------------
# Llamada a llama.cpp server y lectura de la respuesta
# ---------------------------------------------------------------------------
def available() -> bool:
    return bool(settings.LOCAL_MODEL_URL)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.LOCAL_MODEL_API_KEY}"} if settings.LOCAL_MODEL_API_KEY else {}


def complete(prompt: str, max_tokens: int = 512) -> str:
    if not available():
        raise RuntimeError("El servidor no tiene configurado el modelo propio (LOCAL_MODEL_URL).")
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        r = client.post(
            f"{settings.LOCAL_MODEL_URL.rstrip('/')}/completion",
            headers=_headers(),
            json={"prompt": prompt, "n_predict": max_tokens, "temperature": 0.2,
                  "stop": ["<end_of_turn>"], "cache_prompt": True},
        )
    if r.status_code == 401:
        raise RuntimeError("El servidor del modelo propio rechazó la clave (LOCAL_MODEL_API_KEY).")
    r.raise_for_status()
    return r.json().get("content", "")


def health() -> str:
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{settings.LOCAL_MODEL_URL.rstrip('/')}/health", headers=_headers())
    r.raise_for_status()
    return r.json().get("status", "ok")


def _first_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_reply(raw: str) -> tuple[str, list[dict]]:
    """{"say", "actions"} tolerante (bloques ```json, texto alrededor). Sin
    JSON valido, el texto se usa como respuesta y no hay acciones."""
    block = _first_json(raw or "")
    try:
        data = json.loads(block) if block else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return (raw or "").strip(), []
    actions = [a for a in data.get("actions") or []
               if isinstance(a, dict) and isinstance(a.get("tool"), str) and isinstance(a.get("args"), dict)]
    return str(data.get("say") or "").strip(), actions[:MAX_ACTIONS]


# ---------------------------------------------------------------------------
# Consulta completa
# ---------------------------------------------------------------------------
def build_context(snapshot: dict, user_text: str, requester, history, team_context, solutions_enabled) -> dict:
    """Mismo contexto que recibe el modelo del celular (chat_service.device_context)."""
    return {
        "requester_name": getattr(requester, "name", None) or "Alguien",
        "question": user_text,
        "solutions_enabled": bool(solutions_enabled),
        "diagram": snapshot,
        "history": [{"question": q, "answer": a} for q, a in (history or [])],
        "team_context": [
            {"author": m.author, "content": m.content, "is_ai": m.is_ai, "addressed_to": m.addressed_to}
            for m in (team_context or [])
        ],
    }


def run(db, diagram, user_text, requester, history, team_context, mode, solutions_enabled,
        proposals_enabled, label):
    from app.services.ai_assistant import MODE_MENTOR, NO_PROPOSAL_NOTE, AiCommandResult

    executor = DiagramToolExecutor(db, diagram, destructive_confirmed=bool(CONFIRM_RE.search(user_text)))
    snapshot = executor.snapshot()
    revision = ai_proposals.diagram_revision(snapshot)
    prompt = build_prompt(build_context(snapshot, user_text, requester, history, team_context, solutions_enabled))
    say, actions = parse_reply(complete(prompt))
    say = say or "No pude armar una respuesta. ¿Podés reformularlo?"

    if mode == MODE_MENTOR:
        proposal = None
        if actions and proposals_enabled:
            ops, errors, touched = ai_proposals.validate_operations(snapshot, actions)
            if ops and not errors:
                proposal = {"summary": say.split("\n")[0][:300], "operations": ops,
                            "base_hash": ai_proposals.touched_hash(snapshot, touched)}
            else:
                logger.info(f"[MODELO PROPIO] propuesta invalida descartada: {errors}")
        if proposal is None and "propuest" in say.lower():
            say += NO_PROPOSAL_NOTE  # nunca confirmar una propuesta que no quedo registrada
        elif proposal is not None and "propuest" not in say.lower():
            # El modelo (sobre todo antes del reentrenamiento del asesor) puede
            # decir "creé la asociación": en modo asesor NO se aplico nada.
            say += PROPOSAL_NOT_APPLIED_NOTE
        return AiCommandResult(reply=say, actions=[], mode=MODE_MENTOR, proposal=proposal,
                               revision=revision, model_label=label)

    done, failed = [], []
    for a in actions:
        try:
            result = getattr(executor, a["tool"])(**a["args"]) if not a["tool"].startswith("_") and hasattr(executor, a["tool"]) else None
            if result is None:
                raise ToolError(f"La herramienta '{a['tool']}' no existe.")
            done.append({"tool": a["tool"], "input": a["args"], "result": result})
        except ToolError as e:
            failed.append(f"- {e}")
        except TypeError as e:  # argumentos que la herramienta no acepta
            failed.append(f"- {a['tool']}: argumentos inválidos ({e})")
    if failed:
        nota = "\n".join(failed)
        say = (f"No pude aplicar los cambios en el diagrama:\n{nota}" if not done
               else f"{say}\n\nNo pude aplicar todo:\n{nota}")
    return AiCommandResult(reply=say, actions=done, mode="AUTO", revision=revision, model_label=label)
