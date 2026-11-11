# app/services/diagram_vision.py
"""
Lee una imagen de un diagrama -- de clases UML (dibujado a mano, captura o
exportado de otra herramienta) o de base de datos (entidad-relación,
modelo relacional con PK/FK, pata de gallo, Chen) -- y la convierte a la
misma estructura que ya usan el asistente de IA y el import de XMI: clases
con atributos y métodos (notación UML 2.5), y relaciones con su tipo,
multiplicidad, roles y navegabilidad. En un diagrama de base de datos las
tablas son clases y las claves foráneas, relaciones.

Distinto del asistente de edicion (ai_assistant.py): aca no hay ninguna
decision de diseño de parte de la IA -- el diagrama ya existe, dibujado por
una persona en la pizarra, y el modelo solo transcribe lo que ve a datos
estructurados. La restriccion de la catedra ("no generar el diagrama
completo") es sobre inventar un modelo a partir de la descripcion de un
problema; leer una imagen de algo que un humano ya diseño es una
digitalizacion, no un diseño.

El resultado nunca se aplica directo a un diagrama: el router lo devuelve
para que el usuario lo revise (y corrija errores de lectura) en el
frontend antes de confirmarlo.
"""
from __future__ import annotations

import json
import logging
import re
import time

from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.vision import (
    DetectedAttribute, DetectedClass, DetectedMethod, DetectedRelation, VisionDetectResult,
)

logger = logging.getLogger(__name__)

# Formato que entiende _parse_multiplicity en ai_tools.py: "*", un entero
# solo, o "N..M"/"N..*". Una foto real trae letra manuscrita variable, y
# Gemini a veces transcribe cosas como "1,2" (coma en vez de rango) o "1 2"
# que rompen ese parser con un ValueError sin capturar. Mejor descartar acá
# lo que no matchea a None (el backend ya usa 1 como default) que dejar que
# reviente la creacion del diagrama entero por una multiplicidad rara.
_MULTIPLICITY_RE = re.compile(r"^\*$|^\d+$|^\d+\.\.(\d+|\*)$")


def _normalize_multiplicity(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if _MULTIPLICITY_RE.match(value):
        return value
    logger.warning(f"[vision] multiplicidad no reconocida, se descarta: {value!r}")
    return None

MODEL = "gemini-3.5-flash"  # mejor lectura de imagen que el -lite para este caso
# Respaldo si el modelo principal esta saturado (503 sostenido): el -lite
# suele tener menos demanda y sigue leyendo imagenes razonablemente bien.
FALLBACK_MODEL = "gemini-3.5-flash-lite"
REQUEST_TIMEOUT = 90.0

SYSTEM_PROMPT = """Sos un asistente que transcribe a datos estructurados una \
imagen de un diagrama que YA diseñó una persona: puede ser una foto de una \
pizarra o un papel, una captura de pantalla o un diagrama exportado de otra \
herramienta (Enterprise Architect, StarUML, draw.io, MySQL Workbench, \
pgAdmin, DBeaver...). Tu trabajo es leerlo con precisión, no inventar ni \
completar nada que no esté en la imagen.

Primero decidí qué tipo de diagrama es y ponelo en "source":
- "uml": diagrama de clases UML (rectángulos con nombre / atributos / métodos).
- "er": diagrama de base de datos (entidad-relación o modelo relacional: \
  tablas con columnas, claves PK/FK, notación pata de gallo / crow's foot, \
  Chen con rombos, o IDEF1X).

== Diagrama de clases UML ==
Para cada clase:
- Nombre tal cual está escrito. "kind": "interface" si dice «interface»; \
  "enumeration" si dice «enumeration»/«enum»; "abstract" si el nombre está en \
  cursiva o dice {abstract}/«abstract»; si no, "class".
- Atributos (sección del medio): nombre, tipo (lo que sigue a ":"; si no \
  hay, "string"), visibilidad (+ público, - privado, # protegido, ~ paquete; \
  si no está escrita, "-"), is_static si está subrayado, is_derived si \
  empieza con "/", multiplicity si tiene [..] y default_value si tiene "= valor". \
  En una enumeración, cada literal es un atributo (solo el nombre).
- Métodos (tercera sección): nombre, parámetros tal cual entre los \
  paréntesis ("id: int, nombre: string"), tipo de retorno (después de ":"; \
  si no hay, "void"), visibilidad (si no está, "+"), is_static si está \
  subrayado, is_abstract si está en cursiva.
Para cada relación (línea entre dos clases), según la punta:
  - Sin símbolo, o flecha abierta en una línea continua: ASSOCIATION
  - Triángulo hueco en línea continua: INHERITANCE (from_class = hijo, to_class = padre)
  - Triángulo hueco en línea punteada: REALIZATION (from_class = la clase, to_class = la interfaz)
  - Rombo hueco: AGGREGATION; rombo relleno: COMPOSITION. En ambos, \
    from_class = la parte y to_class = el todo (donde está el rombo).
  - Línea punteada con flecha abierta: DEPENDENCY (from_class = quien usa)
  - Si no distinguís el símbolo, ASSOCIATION.
- Multiplicidades escritas en las puntas ("1", "0..1", "1..*", "*"): \
  src_multiplicity es la que está junto a from_class y dst_multiplicity la \
  que está junto a to_class. Si no hay ninguna escrita, dejalas vacías.
- Nombres de rol escritos junto a una punta: src_role / dst_role.
- Navegabilidad: dst_navigable si hay una flecha abierta junto a to_class \
  en una asociación; src_navigable si está junto a from_class.

== Diagrama de base de datos (source = "er") ==
- Cada tabla/entidad es una clase (kind "class"), con el nombre tal cual.
- Cada columna es un atributo con un tipo de esta lista: int, long, \
  string, text, float, double, decimal, boolean, date, datetime, uuid. \
  Traducí los tipos SQL: INT/INTEGER/SMALLINT/SERIAL -> int; \
  BIGINT/BIGSERIAL -> long; VARCHAR/CHAR/NVARCHAR -> string; TEXT/CLOB -> \
  text; NUMERIC/DECIMAL/MONEY -> decimal; REAL/FLOAT -> float; DOUBLE -> \
  double; BOOLEAN/BIT/TINYINT(1) -> boolean; DATE -> date; \
  DATETIME/TIMESTAMP -> datetime; UUID/GUID -> uuid.
- La clave primaria (PK, llave, subrayada) y las columnas NOT NULL van con \
  required=true.
- Una columna que es clave foránea (FK, o que apunta a otra tabla) NO va \
  como atributo: se representa como una relación ASSOCIATION, con \
  from_class = la tabla que tiene la FK y to_class = la tabla referenciada. \
  El backend generado crea esa columna a partir de la relación; si además \
  la dejás como atributo, queda repetida.
- Multiplicidades de cada punta (src_multiplicity junto a from_class, \
  dst_multiplicity junto a to_class), según la notación:
  - Pata de gallo (crow's foot): "pata" sola = "*", raya + pata = "1..*", \
    círculo + pata = "0..*", raya doble o raya sola = "1", círculo + raya = "0..1".
  - Chen (rombo con 1, N, M) o etiquetas "1:N", "1..n": 1 -> "1", N o M -> "*".
  - Sin notación visible en una FK: src_multiplicity "*" y \
    dst_multiplicity "1" (si la FK admite NULL, "0..1").
- Una tabla intermedia de un muchos-a-muchos (solo dos FK, más alguna \
  columna propia) se transcribe como una clase más, con sus dos relaciones.
- En Chen, los óvalos son atributos de la entidad a la que están unidos y \
  el rombo es la relación entre las dos entidades.

Si la imagen no muestra un diagrama de clases ni de base de datos \
reconocible, devolvé listas vacías y un mensaje breve en "warning" \
explicando qué se ve en cambio. Si algo es ilegible, transcribí lo que sí \
se lee y avisalo en "warning".
"""

_ATTRIBUTE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "type": {"type": "STRING"},
        "required": {"type": "BOOLEAN"},
        "visibility": {"type": "STRING", "enum": ["+", "-", "#", "~"]},
        "is_static": {"type": "BOOLEAN"},
        "is_derived": {"type": "BOOLEAN"},
        "multiplicity": {"type": "STRING"},
        "default_value": {"type": "STRING"},
    },
    "required": ["name"],
}

_METHOD_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "params": {"type": "STRING"},
        "return_type": {"type": "STRING"},
        "visibility": {"type": "STRING", "enum": ["+", "-", "#", "~"]},
        "is_static": {"type": "BOOLEAN"},
        "is_abstract": {"type": "BOOLEAN"},
    },
    "required": ["name"],
}

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "source": {"type": "STRING", "enum": ["uml", "er"]},
        "classes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "kind": {"type": "STRING", "enum": ["class", "abstract", "interface", "enumeration"]},
                    "attributes": {"type": "ARRAY", "items": _ATTRIBUTE_SCHEMA},
                    "methods": {"type": "ARRAY", "items": _METHOD_SCHEMA},
                },
                "required": ["name"],
            },
        },
        "relations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "from_class": {"type": "STRING"},
                    "to_class": {"type": "STRING"},
                    "type": {
                        "type": "STRING",
                        "enum": ["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE",
                                 "DEPENDENCY", "REALIZATION"],
                    },
                    "label": {"type": "STRING"},
                    "src_multiplicity": {"type": "STRING"},
                    "dst_multiplicity": {"type": "STRING"},
                    "src_role": {"type": "STRING"},
                    "dst_role": {"type": "STRING"},
                    "src_navigable": {"type": "BOOLEAN"},
                    "dst_navigable": {"type": "BOOLEAN"},
                },
                "required": ["from_class", "to_class", "type"],
            },
        },
        "warning": {"type": "STRING"},
    },
    "required": ["classes", "relations"],
}


# Tipos SQL o de lenguajes que la IA puede devolver igual -> tipos del editor.
_TYPE_ALIASES = {
    "integer": "int", "smallint": "int", "serial": "int", "tinyint": "int",
    "bigint": "long", "bigserial": "long",
    "varchar": "string", "char": "string", "nvarchar": "string", "character varying": "string",
    "clob": "text",
    "numeric": "decimal", "money": "decimal", "bigdecimal": "decimal",
    "real": "float", "double precision": "double",
    "bool": "boolean", "bit": "boolean",
    "timestamp": "datetime", "localdatetime": "datetime", "localdate": "date",
    "guid": "uuid",
}


def _normalize_type(raw: str | None, default: str = "string") -> str:
    """"VARCHAR(80)" -> "string"; los tipos propios (Cliente, EstadoPedido)
    se conservan tal cual."""
    t = (raw or "").strip()
    if not t:
        return default
    base = re.sub(r"\(.*\)$", "", t).strip()
    key = base.lower()
    if key in _TYPE_ALIASES:
        return _TYPE_ALIASES[key]
    if key in ("int", "long", "string", "text", "float", "double", "decimal", "boolean",
               "date", "datetime", "uuid", "void", "email"):
        return key
    return base


_VALID_VIS = {"+", "-", "#", "~"}
_VALID_KINDS = {"class", "abstract", "interface", "enumeration"}


def detect_from_image(image_bytes: bytes, mime_type: str) -> VisionDetectResult:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no esta configurada en el backend (.env).")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def call(model: str):
        return client.models.generate_content(
            model=model,
            contents=[
                SYSTEM_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
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

    # La capa gratuita de Gemini devuelve 503 "high demand" con bastante
    # frecuencia y es tipicamente transitorio (segundos): un par de
    # reintentos cortos con backoff evitan mandar al usuario un error por
    # algo que se resuelve solo con otro intento inmediato. Si el modelo
    # principal sigue saturado despues de esos reintentos, se intenta una
    # vez mas con el modelo -lite (menos demanda) antes de rendirse.
    response = None
    last_error: Exception | None = None
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            response = call(MODEL)
            break
        except Exception as e:
            last_error = e
            if not is_unavailable(e):
                raise
            if attempt == max_attempts - 1:
                # Se agotaron los reintentos con el modelo principal: no
                # relanzar todavia, dejar que caiga al fallback de abajo.
                break
            wait_s = 3 * (attempt + 1)
            logger.warning(f"[vision] intento {attempt + 1} con {MODEL} fallo (503), reintentando en {wait_s}s...")
            time.sleep(wait_s)

    if response is None:
        if last_error is not None and is_unavailable(last_error):
            logger.warning(f"[vision] {MODEL} saturado, probando fallback {FALLBACK_MODEL}...")
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

    raw = response.text or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"[vision] respuesta no parseable como JSON: {raw[:500]!r}")
        raise RuntimeError("El asistente no pudo leer la imagen correctamente. Probá con otra foto, más nítida.")

    def _attr(a: dict) -> DetectedAttribute:
        return DetectedAttribute(
            name=a.get("name", "").strip(),
            type=_normalize_type(a.get("type")),
            required=bool(a.get("required", False)),
            visibility=a.get("visibility") if a.get("visibility") in _VALID_VIS else "-",
            is_static=bool(a.get("is_static", False)),
            is_derived=bool(a.get("is_derived", False)),
            multiplicity=_normalize_multiplicity(a.get("multiplicity")),
            default_value=(a.get("default_value") or "").strip() or None,
        )

    def _method(m: dict) -> DetectedMethod:
        return DetectedMethod(
            name=m.get("name", "").strip().removesuffix("()"),
            params=(m.get("params") or "").strip().removeprefix("(").removesuffix(")").strip(),
            return_type=_normalize_type(m.get("return_type"), default="void"),
            visibility=m.get("visibility") if m.get("visibility") in _VALID_VIS else "+",
            is_static=bool(m.get("is_static", False)),
            is_abstract=bool(m.get("is_abstract", False)),
        )

    classes = [
        DetectedClass(
            name=c.get("name", "").strip(),
            kind=c.get("kind") if c.get("kind") in _VALID_KINDS else "class",
            attributes=[_attr(a) for a in c.get("attributes", []) if a.get("name")],
            methods=[_method(m) for m in c.get("methods", []) if m.get("name")],
        )
        for c in data.get("classes", [])
        if c.get("name")
    ]
    relations = [
        DetectedRelation(
            from_class=r["from_class"].strip(),
            to_class=r["to_class"].strip(),
            type=(r.get("type") or "ASSOCIATION").strip().upper(),
            label=(r.get("label") or "").strip() or None,
            src_multiplicity=_normalize_multiplicity(r.get("src_multiplicity")),
            dst_multiplicity=_normalize_multiplicity(r.get("dst_multiplicity")),
            src_role=(r.get("src_role") or "").strip() or None,
            dst_role=(r.get("dst_role") or "").strip() or None,
            src_navigable=bool(r.get("src_navigable", False)),
            dst_navigable=bool(r.get("dst_navigable", False)),
        )
        for r in data.get("relations", [])
        if r.get("from_class") and r.get("to_class")
    ]

    return VisionDetectResult(
        source=data.get("source") if data.get("source") in ("uml", "er") else "uml",
        classes=classes,
        relations=relations,
        warning=(data.get("warning") or "").strip() or None,
    )
