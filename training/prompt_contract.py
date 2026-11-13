"""
Gemela en Python de mobile/lib/services/assistant_prompt.dart.

El prompt de sistema NO se duplica: se lee del archivo Dart (entre los
marcadores BEGIN_SYSTEM_PROMPT / END_SYSTEM_PROMPT), así el modelo se
entrena con exactamente el mismo texto que usa la app en el celular.
build_user_message() sí está reescrita en Python; su equivalencia con la
versión Dart se verifica contra fixtures/context_example.expected.txt desde
los dos lenguajes (tests/test_prompt_contract.py y
mobile/test/services/assistant_prompt_test.dart).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DART_FILE = ROOT.parent / "mobile" / "lib" / "services" / "assistant_prompt.dart"


def system_prompt() -> str:
    src = DART_FILE.read_text(encoding="utf-8")
    block = src.split("// BEGIN_SYSTEM_PROMPT", 1)[1].split("// END_SYSTEM_PROMPT", 1)[0]
    m = re.search(r"'''(.*?)'''", block, re.S)
    if not m:
        raise RuntimeError(f"No encontré kTeamAssistantSystemPrompt en {DART_FILE}")
    return m.group(1)


def compact_diagram(diagram: dict) -> str:
    lines = []
    for c in diagram.get("clases", []):
        attrs = [f"{a['nombre']}: {a['tipo']}" for a in c.get("atributos", [])]
        methods = [f"{m['nombre']}(): {m['tipo_retorno']}" for m in c.get("metodos", [])]
        body = "; ".join(p for p in (", ".join(attrs), ", ".join(methods)) if p)
        lines.append(f"{c['nombre']}({body})")
    for r in diagram.get("relaciones", []):
        # Con multiplicidades (si vienen): Cliente -[ASSOCIATION 1 → 0..*]-> Pedido.
        mult = (f" {r['mult_origen']} → {r['mult_destino']}"
                if r.get("mult_origen") is not None and r.get("mult_destino") is not None else "")
        lines.append(f"{r['origen']} -[{r['tipo']}{mult}]-> {r['destino']}")
    return "\n".join(lines) if lines else "(vacío)"


def build_user_message(ctx: dict) -> str:
    name = ctx["requester_name"]
    out = [
        f"Quien pregunta: {name}",
        f"Entrega de soluciones: {'ACTIVADA' if ctx.get('solutions_enabled') else 'DESACTIVADA'}",
        "",
        "Diagrama actual:",
        compact_diagram(ctx.get("diagram") or {}),
    ]
    team = ctx.get("team_context") or []
    if team:
        out += ["", "Conversación reciente del equipo:"]
        for m in team:
            if m.get("is_ai"):
                out.append(f"- IA (a {m.get('addressed_to') or 'alguien'}): {m['content']}")
            else:
                out.append(f"- {m['author']}: {m['content']}")
    history = ctx.get("history") or []
    if history:
        out += ["", f"Consultas previas de {name} a la IA:"]
        for h in history:
            out.append(f"- {name}: {h['question']}")
            out.append(f"  IA: {h['answer']}")
    out += ["", f"Consulta actual de {name}: {ctx['question']}"]
    return "\n".join(out)


def gemma_chat(system: str, user: str) -> str:
    return f"<start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n"


def assistant_json(say: str, actions: list[dict] | None = None) -> str:
    """Salida objetivo del modelo (lo que aprende a generar)."""
    return json.dumps({"say": say, "actions": actions or []}, ensure_ascii=False)
