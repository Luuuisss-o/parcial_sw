"""
Propuestas del asesor IA (segundo parcial, CU-06 / CU-07).

El asesor (la IA cuando responde una consulta, modo MENTOR) puede acompañar
su recomendación con una PROPUESTA: operaciones estructuradas sobre el
diagrama, con las mismas herramientas que usa la IA de edición. La
propuesta NO modifica nada: se valida contra el diagrama vigente, se guarda
y se muestra en el chat. Un integrante autorizado (quien preguntó o el
dueño del diagrama) la acepta o la rechaza.

Al aceptarla:
  1. se toma de forma atómica (proposed -> applying): dos personas que
     aceptan a la vez no la aplican dos veces;
  2. si las clases que toca cambiaron desde que se propuso (huella
     distinta), queda STALE y no se aplica a ciegas;
  3. se ejecuta por el mismo servicio de operaciones del primer parcial
     (DiagramToolExecutor), que difunde cada cambio por WebSocket.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chat import AiProposal, ProposalStatus
from app.models.uml import Diagram
from app.models.user import User
from app.services.ai_tools import DiagramToolExecutor, ToolError, _parse_multiplicity, diagram_edit_lock

# Operaciones que el asesor puede proponer (las mismas herramientas de la IA
# de edición, sin move_class: la ubicación no es una decisión de diseño).
PROPOSABLE_TOOLS = (
    "create_class", "rename_class", "delete_class",
    "add_attribute", "delete_attribute",
    "add_method", "delete_method",
    "create_relation", "delete_relation",
)
MAX_OPERATIONS = 25

PROPOSE_TOOL: dict[str, Any] = {
    "name": "propose_changes",
    "description": (
        "Registra una PROPUESTA de cambios sobre el diagrama para que el equipo la revise. "
        "NO modifica nada: queda pendiente hasta que un integrante la acepte. Usala cuando tu "
        "recomendacion implique cambios concretos (relaciones, multiplicidades, atributos o "
        "clases faltantes) sobre clases REALES del diagrama. Para cambiar la multiplicidad o "
        "el tipo de una relacion existente: delete_relation y luego create_relation. "
        "Direccion: herencia hija->padre; agregacion/composicion parte->todo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Que cambia y por que, en una o dos lineas"},
            "operations": {
                "type": "array",
                "description": "Operaciones en orden de aplicacion",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "enum": list(PROPOSABLE_TOOLS)},
                        "args": {
                            "type": "object",
                            "description": (
                                "Argumentos de la herramienta, ej. create_relation: {from_class, to_class, "
                                "type, src_multiplicity, dst_multiplicity}; add_attribute: {class_name, "
                                "name, type, required}"
                            ),
                        },
                    },
                    "required": ["tool", "args"],
                },
            },
        },
        "required": ["summary", "operations"],
    },
}

_REL_TYPES = {"ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"}


# ---------------------------------------------------------------------------
# Huella del diagrama (revision) y de las clases que toca una propuesta
# ---------------------------------------------------------------------------
def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def diagram_revision(snapshot: dict) -> str:
    """Revision del diagrama: cambia con cualquier cambio de clases,
    atributos, metodos o relaciones (no con mover una clase)."""
    clases = sorted(
        (c["nombre"], sorted((a["nombre"], a["tipo"], a["requerido"]) for a in c["atributos"]),
         sorted((m["nombre"], m["tipo_retorno"]) for m in c["metodos"]))
        for c in snapshot["clases"]
    )
    rels = sorted(tuple(str(r.get(k)) for k in ("origen", "destino", "tipo", "mult_origen", "mult_destino"))
                  for r in snapshot["relaciones"])
    return _digest([clases, rels])[:16]


def touched_hash(snapshot: dict, touched: set[str]) -> str:
    """Huella de lo que toca la propuesta: las clases nombradas (o su
    ausencia, si la propuesta las crea) y las relaciones entre ellas."""
    by_name = {c["nombre"].lower(): c for c in snapshot["clases"]}
    parts = []
    for name in sorted(touched):
        c = by_name.get(name)
        parts.append([name, None] if c is None else [
            name,
            sorted((a["nombre"], a["tipo"], a["requerido"]) for a in c["atributos"]),
            sorted((m["nombre"], m["tipo_retorno"]) for m in c["metodos"]),
        ])
    rels = sorted(
        tuple(str(r.get(k)) for k in ("origen", "destino", "tipo", "mult_origen", "mult_destino"))
        for r in snapshot["relaciones"]
        if r["origen"].lower() in touched or r["destino"].lower() in touched
    )
    return _digest([parts, rels])


# ---------------------------------------------------------------------------
# Validacion sin ejecutar (sobre una copia en memoria del diagrama)
# ---------------------------------------------------------------------------
def validate_operations(snapshot: dict, operations: Any) -> tuple[list[dict], list[str], set[str]]:
    """Simula las operaciones sobre el diagrama vigente. Devuelve
    (operaciones normalizadas, errores, nombres de clase tocados en minuscula)."""
    errors: list[str] = []
    clean: list[dict] = []
    touched: set[str] = set()
    if not isinstance(operations, list) or not operations:
        return [], ["La propuesta no trae operaciones."], touched
    if len(operations) > MAX_OPERATIONS:
        return [], [f"Demasiadas operaciones ({len(operations)}); el maximo es {MAX_OPERATIONS}."], touched

    classes: dict[str, dict] = {
        c["nombre"].lower(): {
            "nombre": c["nombre"],
            "attrs": {a["nombre"].lower() for a in c["atributos"]},
            "meths": {m["nombre"].lower() for m in c["metodos"]},
        }
        for c in snapshot["clases"]
    }
    rels = [(r["origen"].lower(), r["destino"].lower(), r["tipo"]) for r in snapshot["relaciones"]]

    def need_class(name: Any, i: int) -> str | None:
        key = str(name or "").strip().lower()
        touched.add(key)
        if key not in classes:
            errors.append(f"Operacion {i}: la clase '{name}' no existe en el diagrama.")
            return None
        return key

    for i, op in enumerate(operations, 1):
        if not isinstance(op, dict) or op.get("tool") not in PROPOSABLE_TOOLS or not isinstance(op.get("args"), dict):
            errors.append(f"Operacion {i}: formato invalido o herramienta no permitida ({op!r:.80}).")
            continue
        tool, args = op["tool"], {k: v for k, v in op["args"].items() if v is not None}
        if tool == "create_class":
            key = str(args.get("name", "")).strip().lower()
            touched.add(key)
            if not key:
                errors.append(f"Operacion {i}: create_class sin nombre.")
            elif key in classes:
                errors.append(f"Operacion {i}: la clase '{args['name']}' ya existe.")
            else:
                classes[key] = {"nombre": args["name"].strip(), "attrs": set(), "meths": set()}
                args = {"name": args["name"].strip()}
        elif tool == "rename_class":
            key = need_class(args.get("class_name"), i)
            new = str(args.get("new_name", "")).strip()
            touched.add(new.lower())
            if key and (not new or new.lower() in classes):
                errors.append(f"Operacion {i}: nombre nuevo invalido o ya usado ('{new}').")
            elif key:
                classes[new.lower()] = {**classes.pop(key), "nombre": new}
                rels = [(new.lower() if o == key else o, new.lower() if d == key else d, t) for o, d, t in rels]
        elif tool == "delete_class":
            key = need_class(args.get("class_name"), i)
            if key:
                classes.pop(key)
                rels = [r for r in rels if key not in (r[0], r[1])]
        elif tool in ("add_attribute", "delete_attribute", "add_method", "delete_method"):
            key = need_class(args.get("class_name"), i)
            if not key:
                continue
            bucket = "attrs" if "attribute" in tool else "meths"
            name_arg = "name" if tool.startswith("add") else ("attribute_name" if bucket == "attrs" else "method_name")
            member = str(args.get(name_arg, "")).strip().lower()
            if not member or (tool == "add_attribute" and not str(args.get("type", "")).strip()):
                errors.append(f"Operacion {i}: faltan datos para {tool}.")
            elif tool.startswith("add") and member in classes[key][bucket]:
                errors.append(f"Operacion {i}: '{classes[key]['nombre']}' ya tiene '{args[name_arg]}'.")
            elif tool.startswith("delete") and member not in classes[key][bucket]:
                errors.append(f"Operacion {i}: '{classes[key]['nombre']}' no tiene '{args[name_arg]}'.")
            else:
                (classes[key][bucket].add if tool.startswith("add") else classes[key][bucket].discard)(member)
        elif tool in ("create_relation", "delete_relation"):
            a, b = need_class(args.get("from_class"), i), need_class(args.get("to_class"), i)
            rtype = str(args.get("type") or ("ASSOCIATION" if tool == "create_relation" else "")).upper()
            if rtype and rtype not in _REL_TYPES:
                errors.append(f"Operacion {i}: tipo de relacion invalido '{args.get('type')}'.")
                continue
            if not (a and b):
                continue
            if tool == "create_relation":
                dup = [r for r in rels if r[2] == rtype and {r[0], r[1]} == {a, b}]
                if dup and rtype != "INHERITANCE" or (rtype == "INHERITANCE" and (a, b, rtype) in rels):
                    errors.append(
                        f"Operacion {i}: ya existe una relacion {rtype} entre '{args.get('from_class')}' y "
                        f"'{args.get('to_class')}'. Para cambiar su multiplicidad o tipo, primero "
                        f"delete_relation y despues create_relation."
                    )
                    continue
                try:
                    for side in ("src_multiplicity", "dst_multiplicity"):
                        if args.get(side) is not None:
                            _parse_multiplicity(str(args[side]))
                except ValueError:
                    errors.append(f"Operacion {i}: multiplicidad invalida.")
                    continue
                args["type"] = rtype
                rels.append((a, b, rtype))
            else:
                match = [r for r in rels if r[0] == a and r[1] == b and (not rtype or r[2] == rtype)]
                if len(match) != 1:
                    errors.append(f"Operacion {i}: no hay una unica relacion {args.get('from_class')} -> {args.get('to_class')} para eliminar.")
                    continue
                rels.remove(match[0])
                if rtype:
                    args["type"] = rtype
        clean.append({"tool": tool, "args": args})
    touched.discard("")
    return clean, errors, touched


def describe(op: dict) -> str:
    """Texto legible de una operacion (para mostrar el impacto antes de aceptar)."""
    t, a = op["tool"], op["args"]
    if t == "create_class":
        return f"Crear la clase {a['name']}"
    if t == "rename_class":
        return f"Renombrar {a['class_name']} a {a['new_name']}"
    if t == "delete_class":
        return f"Eliminar la clase {a['class_name']} (con sus atributos y relaciones)"
    if t == "add_attribute":
        return f"Agregar a {a['class_name']} el atributo {a['name']}: {a['type']}" + (" (obligatorio)" if a.get("required") else "")
    if t == "delete_attribute":
        return f"Quitar de {a['class_name']} el atributo {a['attribute_name']}"
    if t == "add_method":
        return f"Agregar a {a['class_name']} el método {a['name']}(): {a.get('return_type', 'void')}"
    if t == "delete_method":
        return f"Quitar de {a['class_name']} el método {a['method_name']}"
    if t == "create_relation":
        mult = ""
        if a.get("src_multiplicity") or a.get("dst_multiplicity"):
            mult = f" ({a.get('src_multiplicity', '1')} → {a.get('dst_multiplicity', '1')})"
        return f"Relacionar {a['from_class']} → {a['to_class']}: {a['type']}{mult}"
    if t == "delete_relation":
        return f"Eliminar la relación {a['from_class']} → {a['to_class']}" + (f" ({a['type']})" if a.get("type") else "")
    return t


# ---------------------------------------------------------------------------
# Persistencia y decision
# ---------------------------------------------------------------------------
def create(db: Session, diagram: Diagram, *, draft: dict, question_id, message_id, requester) -> AiProposal:
    p = AiProposal(
        diagram_id=diagram.id,
        question_id=question_id,
        message_id=message_id,
        requested_by_id=getattr(requester, "user_id", None),
        requested_by_name=getattr(requester, "name", None),
        summary=draft["summary"],
        operations=draft["operations"],
        base_hash=draft["base_hash"],
        status=ProposalStatus.PROPOSED.value,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def payload(p: AiProposal) -> dict:
    return {
        "id": str(p.id),
        "message_id": str(p.message_id) if p.message_id else None,
        "status": p.status,
        "summary": p.summary,
        "operations": p.operations,
        "changes": [describe(op) for op in p.operations],
        "requested_by_id": p.requested_by_id,
        "requested_by_name": p.requested_by_name,
        # La web compara con el email de la sesion para saber si puede decidir.
        "requested_by_email": p.requested_by.email if p.requested_by else None,
        "decided_by_name": p.decided_by_name,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "result": p.result,
    }


class ProposalError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def can_decide(p: AiProposal, diagram: Diagram, user: User) -> bool:
    """Acepta o rechaza quien hizo la consulta o el dueño del diagrama."""
    return user.id in (p.requested_by_id, diagram.owner_id)


def decide(db: Session, diagram: Diagram, proposal_id: UUID, user: User, accept: bool) -> AiProposal:
    p = db.get(AiProposal, proposal_id)
    if p is None or p.diagram_id != diagram.id:
        raise ProposalError(404, "Propuesta no encontrada")
    if not can_decide(p, diagram, user):
        raise ProposalError(403, "Solo quien hizo la consulta o el dueño del diagrama puede decidir esta propuesta")

    # Toma atomica: solo una decision gana aunque dos personas acepten a la vez.
    claimed = (
        db.query(AiProposal)
        .filter(AiProposal.id == p.id, AiProposal.status == ProposalStatus.PROPOSED.value)
        .update({AiProposal.status: "applying" if accept else ProposalStatus.REJECTED.value},
                synchronize_session=False)
    )
    db.commit()
    db.refresh(p)
    if claimed == 0:
        raise ProposalError(409, f"La propuesta ya no está pendiente (estado: {p.status})")

    p.decided_by_id, p.decided_by_name = user.id, user.name
    p.decided_at = datetime.datetime.now(datetime.timezone.utc)
    if not accept:
        db.commit()
        return p

    # Con el lock del diagrama tomado de punta a punta: otra consulta de la IA
    # no puede editar entre la verificación de "desactualizada" y la
    # aplicación (las ediciones de la IA se serializan por diagrama).
    with diagram_edit_lock(diagram.id):
        executor = DiagramToolExecutor(db, diagram, destructive_confirmed=True,  # aceptar = confirmar
                                       actor_email=user.email)
        db.flush()
        db.expire_all()
        snapshot = executor.snapshot()
        _, errors, touched = validate_operations(snapshot, p.operations)
        if errors or touched_hash(snapshot, touched) != p.base_hash:
            p.status = ProposalStatus.STALE.value
            p.result = [{"ok": False, "message": e} for e in errors] or [
                {"ok": False, "message": "Las clases involucradas cambiaron desde que se propuso: pedile al asesor una revisión nueva."}
            ]
            db.commit()
            return p

        results = []
        for op in p.operations:
            try:
                getattr(executor, op["tool"])(**op["args"])
                results.append({"ok": True, "message": describe(op)})
            except ToolError as e:
                db.rollback()
                results.append({"ok": False, "message": f"{describe(op)}: {e}"})
                break  # no seguir sobre un estado que ya no es el esperado
        p.result = results
        p.status = ProposalStatus.APPLIED.value if all(r["ok"] for r in results) else ProposalStatus.FAILED.value
        db.commit()
        return p
