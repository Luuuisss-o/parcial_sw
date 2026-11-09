# app/services/ai_tools.py
"""
Herramientas (tools) que el asistente de IA puede invocar para editar un
diagrama UML. Cada tool hace exactamente lo mismo que el endpoint REST
equivalente (mismo modelo, misma notificacion realtime por WebSocket) pero
resuelve clases/relaciones por nombre en vez de UUID, porque el usuario le
habla al asistente por nombre ("la clase Cliente"), no por id.

Restriccion pedida por la catedra: el asistente NUNCA genera el diagrama
completo de una sola vez. Cada tool es una edicion puntual; es el modelo de
IA quien decide, comando a comando, que tools llamar.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.uml import Atributo, Clase, Diagram, Metodo, RelType, Relacion
from app.schemas.relacion import RelacionOut
from app.utils import realtime_events

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Error esperado (ej. 'no existe la clase X') que se le devuelve al modelo
    como resultado de error para que pueda corregirse o preguntar."""


_fire = realtime_events.fire


# El usuario confirmo explicitamente una eliminacion: "confirmo ..." o, AL
# COMIENZO, "si" con tilde o seguido de coma ("si, eliminala"). Asi el
# condicional "si eliminas X, que pasa?" no cuenta como confirmacion.
CONFIRM_RE = re.compile(
    r"\bconfirm\w*|^\s*(?:@\w+[\s,]*)?s(?:í[\s,]+|i\s*,\s*)(?:elimin|borr|quit)\w*", re.IGNORECASE
)
CONFIRMATION_REQUIRED = "CONFIRMACION REQUERIDA"


class DiagramToolExecutor:
    """Ejecuta tools sobre un diagrama concreto, ya validado como propiedad del usuario.

    `destructive_confirmed=False` (lo usa el asistente cuando el mensaje del
    usuario no trae una confirmacion explicita): borrar una clase que tiene
    atributos, metodos o relaciones -- se pierden en cascada -- o hacer mas de
    una eliminacion en el mismo pedido se rechaza con CONFIRMACION REQUERIDA,
    y el modelo tiene que pedirle confirmacion al usuario. Es una regla del
    servidor, no del criterio del modelo."""

    def __init__(self, db: Session, diagram: Diagram, destructive_confirmed: bool = True):
        self.db = db
        self.diagram = diagram
        self.destructive_confirmed = destructive_confirmed
        self._destructive_done = 0

    def _guard_destructive(self, what: str, impact: str = "") -> None:
        if not self.destructive_confirmed and (impact or self._destructive_done >= 1):
            motivo = (f"eliminar {what} borra tambien {impact}" if impact
                      else "el pedido incluye varias eliminaciones")
            raise ToolError(
                f"{CONFIRMATION_REQUIRED}: no elimine nada ({motivo}). Explicale al usuario "
                f"que se perderia y pedile que confirme escribiendo, por ejemplo: "
                f"'@IA confirmo, elimina {what}'."
            )
        self._destructive_done += 1

    # ---------------------------------------------------------------
    # Resolucion de nombres -> entidades (case-insensitive)
    # ---------------------------------------------------------------
    def _find_class(self, name: str) -> Clase:
        c = (
            self.db.query(Clase)
            .filter(Clase.diagram_id == self.diagram.id)
            .filter(Clase.nombre.ilike(name.strip()))
            .one_or_none()
        )
        if not c:
            existentes = [c.nombre for c in self.db.query(Clase).filter(Clase.diagram_id == self.diagram.id)]
            raise ToolError(
                f"No existe una clase llamada '{name}' en este diagrama. "
                f"Clases existentes: {', '.join(existentes) or '(ninguna todavia)'}."
            )
        return c

    def _find_attribute(self, clase: Clase, name: str) -> Atributo:
        a = (
            self.db.query(Atributo)
            .filter(Atributo.clase_id == clase.id)
            .filter(Atributo.nombre.ilike(name.strip()))
            .one_or_none()
        )
        if not a:
            raise ToolError(f"La clase '{clase.nombre}' no tiene un atributo llamado '{name}'.")
        return a

    def _find_method(self, clase: Clase, name: str) -> Metodo:
        m = (
            self.db.query(Metodo)
            .filter(Metodo.clase_id == clase.id)
            .filter(Metodo.nombre.ilike(name.strip()))
            .one_or_none()
        )
        if not m:
            raise ToolError(f"La clase '{clase.nombre}' no tiene un metodo llamado '{name}'.")
        return m

    # ---------------------------------------------------------------
    # Snapshot para darle contexto a Claude del estado actual
    # ---------------------------------------------------------------
    def snapshot(self) -> dict:
        classes = self.db.query(Clase).filter(Clase.diagram_id == self.diagram.id).all()
        out = []
        for c in classes:
            out.append({
                "nombre": c.nombre,
                "x_grid": c.x_grid, "y_grid": c.y_grid,
                "w_grid": c.w_grid, "h_grid": c.h_grid,
                "atributos": [
                    {"nombre": a.nombre, "tipo": a.tipo, "requerido": a.requerido}
                    for a in c.atributos
                ],
                "metodos": [
                    {"nombre": m.nombre, "tipo_retorno": m.tipo_retorno}
                    for m in c.metodos
                ],
            })
        rels = (
            self.db.query(Relacion)
            .filter(Relacion.diagram_id == self.diagram.id)
            .all()
        )
        rels_out = [
            {
                "origen": r.origen.nombre,
                "destino": r.destino.nombre,
                "tipo": r.tipo.value,
                "etiqueta": r.etiqueta,
            }
            for r in rels
        ]
        return {"clases": out, "relaciones": rels_out}

    # ---------------------------------------------------------------
    # Clases
    # ---------------------------------------------------------------
    def create_class(self, name: str, x_grid: Optional[int] = None, y_grid: Optional[int] = None) -> dict:
        existing = (
            self.db.query(Clase)
            .filter(Clase.diagram_id == self.diagram.id)
            .filter(Clase.nombre.ilike(name.strip()))
            .one_or_none()
        )
        if existing:
            raise ToolError(f"Ya existe una clase llamada '{name}' en este diagrama.")

        # Las coordenadas que propone el modelo se toman como sugerencia: si
        # faltan o caen encima de otra clase (Gemini suele mandar posiciones
        # chicas como (1,1) y (3,1) para clases distintas), se busca un lugar
        # libre en la grilla.
        if x_grid is None or y_grid is None or self._overlaps(x_grid, y_grid):
            x_grid, y_grid = self._free_slot()
        c = Clase(
            nombre=name.strip(),
            diagram_id=self.diagram.id,
            x_grid=x_grid,
            y_grid=y_grid,
        )
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        _fire(realtime_events.notify_class_created(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre}

    # Tamaño reservado por clase al ubicarla sola: el ancho por defecto (12) y
    # un alto holgado, porque la tarjeta crece al agregarle atributos.
    _SLOT_W, _SLOT_H, _SLOT_GAP, _SLOT_COLS = 12, 10, 4, 4

    def _occupied(self) -> list[tuple[int, int, int, int]]:
        return [
            (c.x_grid, c.y_grid, c.x_grid + max(c.w_grid, self._SLOT_W), c.y_grid + max(c.h_grid, self._SLOT_H))
            for c in self.db.query(Clase).filter(Clase.diagram_id == self.diagram.id)
        ]

    def _overlaps(self, x: int, y: int, rects=None) -> bool:
        g = self._SLOT_GAP // 2
        box = (x - g, y - g, x + self._SLOT_W + g, y + self._SLOT_H + g)
        rects = self._occupied() if rects is None else rects
        return any(box[0] < r[2] and r[0] < box[2] and box[1] < r[3] and r[1] < box[3] for r in rects)

    def _free_slot(self) -> tuple[int, int]:
        """Primera celda libre de una grilla imaginaria (de izquierda a derecha
        y de arriba a abajo) que no se superpone con ninguna clase existente.

        Antes, si el modelo no indicaba coordenadas (lo normal), todas las
        clases creadas por la IA quedaban en (0, 0), una encima de la otra."""
        rects = self._occupied()
        step_x, step_y = self._SLOT_W + self._SLOT_GAP, self._SLOT_H + self._SLOT_GAP
        for i in range(400):
            x, y = (i % self._SLOT_COLS) * step_x, (i // self._SLOT_COLS) * step_y
            if not self._overlaps(x, y, rects):
                return x, y
        return 0, (len(rects) // self._SLOT_COLS + 1) * step_y

    def rename_class(self, class_name: str, new_name: str) -> dict:
        c = self._find_class(class_name)
        c.nombre = new_name.strip()
        self.db.commit()
        self.db.refresh(c)
        _fire(realtime_events.notify_class_updated(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre}

    def move_class(self, class_name: str, x_grid: int, y_grid: int) -> dict:
        c = self._find_class(class_name)
        c.x_grid, c.y_grid = x_grid, y_grid
        self.db.commit()
        self.db.refresh(c)
        _fire(realtime_events.notify_class_updated(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre, "x_grid": c.x_grid, "y_grid": c.y_grid}

    def delete_class(self, class_name: str) -> dict:
        c = self._find_class(class_name)
        n_rel = (
            self.db.query(Relacion)
            .filter((Relacion.origen_id == c.id) | (Relacion.destino_id == c.id))
            .count()
        )
        parts = [f"{n} {label}" for n, label in (
            (len(c.atributos), "atributo(s)"), (len(c.metodos), "metodo(s)"), (n_rel, "relacion(es)"),
        ) if n]
        self._guard_destructive(f"la clase '{c.nombre}'", ", ".join(parts))
        class_id = c.id
        self.db.delete(c)
        self.db.commit()
        _fire(realtime_events.notify_class_deleted(self.diagram.id, class_id))
        return {"ok": True, "clase": class_name}

    # ---------------------------------------------------------------
    # Atributos
    # ---------------------------------------------------------------
    def add_attribute(self, class_name: str, name: str, type: str, required: bool = False) -> dict:
        c = self._find_class(class_name)
        existing = (
            self.db.query(Atributo)
            .filter(Atributo.clase_id == c.id)
            .filter(Atributo.nombre.ilike(name.strip()))
            .one_or_none()
        )
        if existing:
            raise ToolError(f"La clase '{c.nombre}' ya tiene un atributo llamado '{name}'.")
        a = Atributo(nombre=name.strip(), tipo=type.strip(), requerido=bool(required), clase_id=c.id)
        self.db.add(a)
        self.db.commit()
        self.db.refresh(a)
        _fire(realtime_events.notify_attribute_created(self.diagram.id, a))
        _fire(realtime_events.notify_class_updated(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre, "atributo": a.nombre, "tipo": a.tipo}

    def delete_attribute(self, class_name: str, attribute_name: str) -> dict:
        c = self._find_class(class_name)
        a = self._find_attribute(c, attribute_name)
        self._guard_destructive(f"el atributo '{a.nombre}' de '{c.nombre}'")
        attr_id = a.id
        self.db.delete(a)
        self.db.commit()
        _fire(realtime_events.notify_attribute_deleted(self.diagram.id, attr_id, c.id))
        _fire(realtime_events.notify_class_updated(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre, "atributo": attribute_name}

    # ---------------------------------------------------------------
    # Metodos
    # ---------------------------------------------------------------
    def add_method(self, class_name: str, name: str, return_type: str = "void") -> dict:
        c = self._find_class(class_name)
        existing = (
            self.db.query(Metodo)
            .filter(Metodo.clase_id == c.id)
            .filter(Metodo.nombre.ilike(name.strip()))
            .one_or_none()
        )
        if existing:
            raise ToolError(f"La clase '{c.nombre}' ya tiene un metodo llamado '{name}'.")
        m = Metodo(nombre=name.strip(), tipo_retorno=return_type.strip(), clase_id=c.id)
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        _fire(realtime_events.notify_method_created(self.diagram.id, m))
        _fire(realtime_events.notify_class_updated(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre, "metodo": m.nombre}

    def delete_method(self, class_name: str, method_name: str) -> dict:
        c = self._find_class(class_name)
        m = self._find_method(c, method_name)
        self._guard_destructive(f"el metodo '{m.nombre}' de '{c.nombre}'")
        method_id = m.id
        self.db.delete(m)
        self.db.commit()
        _fire(realtime_events.notify_method_deleted(self.diagram.id, method_id, c.id))
        _fire(realtime_events.notify_class_updated(self.diagram.id, c))
        return {"ok": True, "clase": c.nombre, "metodo": method_name}

    # ---------------------------------------------------------------
    # Relaciones
    # ---------------------------------------------------------------
    def create_relation(
        self,
        from_class: str,
        to_class: str,
        type: str,
        label: Optional[str] = None,
        src_multiplicity: Optional[str] = None,
        dst_multiplicity: Optional[str] = None,
        es_clase_asociacion: bool = False,
    ) -> dict:
        src = self._find_class(from_class)
        dst = self._find_class(to_class)
        try:
            rel_type = RelType(type.strip().upper())
        except ValueError:
            raise ToolError(
                f"Tipo de relacion invalido: '{type}'. Valores validos: "
                f"{', '.join(t.value for t in RelType)}."
            )

        src_min, src_max = _parse_multiplicity(src_multiplicity)
        dst_min, dst_max = _parse_multiplicity(dst_multiplicity)

        r = Relacion(
            diagram_id=self.diagram.id,
            origen_id=src.id,
            destino_id=dst.id,
            tipo=rel_type,
            etiqueta=label,
            mult_origen_min=src_min, mult_origen_max=src_max,
            mult_destino_min=dst_min, mult_destino_max=dst_max,
            es_clase_asociacion=es_clase_asociacion,
        )
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)

        rel_out = RelacionOut.model_validate({
            **r.__dict__,
            "origen_nombre": src.nombre,
            "destino_nombre": dst.nombre,
        })
        _fire(realtime_events.notify_relation_created(self.diagram.id, rel_out))
        return {"ok": True, "origen": src.nombre, "destino": dst.nombre, "tipo": rel_type.value}

    def delete_relation(self, from_class: str, to_class: str, type: Optional[str] = None) -> dict:
        src = self._find_class(from_class)
        dst = self._find_class(to_class)
        q = (
            self.db.query(Relacion)
            .filter(
                Relacion.diagram_id == self.diagram.id,
                Relacion.origen_id == src.id,
                Relacion.destino_id == dst.id,
            )
        )
        if type:
            try:
                q = q.filter(Relacion.tipo == RelType(type.strip().upper()))
            except ValueError:
                raise ToolError(f"Tipo de relacion invalido: '{type}'.")

        rels = q.all()
        if not rels:
            raise ToolError(f"No hay relacion entre '{src.nombre}' y '{dst.nombre}'.")
        if len(rels) > 1:
            tipos = ", ".join(r.tipo.value for r in rels)
            raise ToolError(
                f"Hay mas de una relacion entre '{src.nombre}' y '{dst.nombre}' ({tipos}). "
                f"Especifica el tipo para eliminar una sola."
            )

        r = rels[0]
        self._guard_destructive(f"la relacion entre '{src.nombre}' y '{dst.nombre}'")
        relation_id = r.id
        self.db.delete(r)
        self.db.commit()
        _fire(realtime_events.notify_relation_deleted(self.diagram.id, relation_id))
        return {"ok": True, "origen": src.nombre, "destino": dst.nombre}


def _parse_multiplicity(value: Optional[str]) -> tuple[int, Optional[int]]:
    """Convierte '0..1' / '1' / '1..*' / '*' -> (min, max) donde max=None significa '*'."""
    if not value:
        return 1, None
    value = value.strip()
    if value == "*":
        return 0, None
    if ".." in value:
        lo, hi = value.split("..", 1)
        lo = int(lo)
        hi = None if hi.strip() == "*" else int(hi)
        return lo, hi
    n = int(value)
    return n, n


# =====================================================================
# Definicion de tools (json schema por tool, neutral respecto al proveedor)
# =====================================================================
_RAW_TOOLS: list[dict[str, Any]] = [
    {
        "name": "create_class",
        "description": "Crea una clase nueva y vacia en el diagrama. Usar cuando el usuario pide crear/agregar una clase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre de la clase"},
                "x_grid": {"type": "integer", "description": "Posicion horizontal en la grilla. Omitir salvo que el usuario pida una ubicacion concreta: el sistema ubica la clase en un lugar libre."},
                "y_grid": {"type": "integer", "description": "Posicion vertical en la grilla. Omitir salvo que el usuario pida una ubicacion concreta."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "rename_class",
        "description": "Cambia el nombre de una clase existente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string", "description": "Nombre actual de la clase"},
                "new_name": {"type": "string", "description": "Nuevo nombre"},
            },
            "required": ["class_name", "new_name"],
        },
    },
    {
        "name": "move_class",
        "description": "Mueve una clase a una nueva posicion en la grilla del diagrama.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string"},
                "x_grid": {"type": "integer"},
                "y_grid": {"type": "integer"},
            },
            "required": ["class_name", "x_grid", "y_grid"],
        },
    },
    {
        "name": "delete_class",
        "description": "Elimina una clase del diagrama (y sus atributos, metodos y relaciones).",
        "input_schema": {
            "type": "object",
            "properties": {"class_name": {"type": "string"}},
            "required": ["class_name"],
        },
    },
    {
        "name": "add_attribute",
        "description": "Agrega un atributo a una clase existente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string"},
                "name": {"type": "string", "description": "Nombre del atributo"},
                "type": {"type": "string", "description": "Tipo de dato, ej: String, Integer, Boolean, LocalDate"},
                "required": {"type": "boolean", "description": "Si el atributo es obligatorio (default false)"},
            },
            "required": ["class_name", "name", "type"],
        },
    },
    {
        "name": "delete_attribute",
        "description": "Elimina un atributo de una clase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string"},
                "attribute_name": {"type": "string"},
            },
            "required": ["class_name", "attribute_name"],
        },
    },
    {
        "name": "add_method",
        "description": "Agrega un metodo (operacion) a una clase existente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string"},
                "name": {"type": "string"},
                "return_type": {"type": "string", "description": "Tipo de retorno, default 'void'"},
            },
            "required": ["class_name", "name"],
        },
    },
    {
        "name": "delete_method",
        "description": "Elimina un metodo de una clase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string"},
                "method_name": {"type": "string"},
            },
            "required": ["class_name", "method_name"],
        },
    },
    {
        "name": "create_relation",
        "description": (
            "Crea una relacion UML entre dos clases existentes. DIRECCION (importa: "
            "el editor dibuja el rombo/flecha en el destino y el backend generado "
            "se arma a partir de ella): INHERITANCE -> from_class = subclase (hija), "
            "to_class = superclase (padre). AGGREGATION/COMPOSITION -> from_class = "
            "la PARTE, to_class = el TODO; ej. 'Pedido se compone de DetallePedido' "
            "-> from_class=DetallePedido, to_class=Pedido. ASSOCIATION/DEPENDENCY: "
            "en el orden en que el usuario las nombra."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_class": {"type": "string", "description": "Clase origen (hija en herencia, parte en agregacion/composicion)"},
                "to_class": {"type": "string", "description": "Clase destino (padre en herencia, todo en agregacion/composicion)"},
                "type": {
                    "type": "string",
                    "enum": ["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"],
                },
                "label": {"type": "string", "description": "Etiqueta opcional de la relacion"},
                "src_multiplicity": {
                    "type": "string",
                    "description": "Multiplicidad del lado origen, ej '1', '0..1', '1..*', '*' (default 1)",
                },
                "dst_multiplicity": {
                    "type": "string",
                    "description": "Multiplicidad del lado destino, ej '1', '0..1', '1..*', '*' (default 1)",
                },
            },
            "required": ["from_class", "to_class", "type"],
        },
    },
    {
        "name": "delete_relation",
        "description": "Elimina la relacion entre dos clases. Si hay mas de una entre ellas, especificar el tipo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_class": {"type": "string"},
                "to_class": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"],
                },
            },
            "required": ["from_class", "to_class"],
        },
    },
]

# Formato que espera el SDK de Gemini (google-genai): function schema con
# "parameters" en vez de "input_schema", y "type": "function" explicito.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": t["name"],
        "description": t["description"],
        "parameters": t["input_schema"],
    }
    for t in _RAW_TOOLS
]


# Formato OpenAI "chat completions" (lo hablan Ollama, LM Studio, vLLM,
# llama.cpp server y el endpoint OpenAI-compatible de Gemini): cada tool va
# envuelta en {"type": "function", "function": {...}}.
OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in _RAW_TOOLS
]
