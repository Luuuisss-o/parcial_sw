"""
Genera el dataset para PERSONALIZAR (fine-tuning con LoRA) el modelo que
corre en el celular como integrante IA del equipo (Fase 2).

Cada ejemplo es una conversación de un turno en el formato exacto que usa la
app (mobile/lib/services/assistant_prompt.dart):

    user:      <prompt de sistema>\n\n<contexto: quién pregunta, diagrama,
               conversación del equipo, hilo propio, consulta>
    assistant: {"say": "Ana, ...", "actions": [{"tool": ..., "args": ...}]}

Fuentes:
  1. Ediciones del diagrama, generadas por plantillas (crear clases,
     atributos con tipo inferido, relaciones con multiplicidad, métodos,
     renombrar, borrar, varias acciones a la vez).
  2. Mentoría: respuestas pedagógicas DESTILADAS de un modelo maestro
     (Gemini) para data/mentor_questions.txt -> data/teacher_mentor.jsonl.
  3. Soluciones completas (para cuando el dueño las habilita), también del
     maestro -> data/teacher_solutions.jsonl.
  4. Comportamientos del chat grupal: dirigirse por nombre, usar el hilo
     propio ("agregale otro atributo"), usar lo que dijo el equipo, y
     respetar la configuración de entrega de soluciones.

Uso:
    # (opcional) regenerar las respuestas del maestro; requiere GEMINI_API_KEY
    python build_dataset.py --teacher
    # armar train.jsonl / eval.jsonl con lo que ya hay en data/
    python build_dataset.py

Los archivos del maestro quedan versionados en data/, así el dataset se
puede reconstruir sin volver a llamar a ninguna API.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import prompt_contract as pc  # noqa: E402

DATA = ROOT / "data"
TEACHER_MENTOR = DATA / "teacher_mentor.jsonl"
TEACHER_SOLUTIONS = DATA / "teacher_solutions.jsonl"

# ---------------------------------------------------------------------------
# Vocabulario
# ---------------------------------------------------------------------------
PEOPLE = [
    "Ana Pérez", "Bruno Díaz", "Carla Ruiz", "Diego Mamani", "Elena Rojas", "Fernando Vaca",
    "Gabriela Suárez", "Hugo Flores", "Inés Gutiérrez", "Javier Rivero", "Karen Justiniano",
    "Luis Gabriel", "María Choque", "Nicolás Paz", "Olivia Montaño", "Pablo Arce",
    "Romer Rojas", "Sofía Vargas", "Trébor Medina", "Valeria Ortiz",
]

DOMAINS = {
    "ventas": {
        "Cliente": [("nombre", "String"), ("email", "String"), ("telefono", "String"), ("nit", "String")],
        "Pedido": [("fecha", "LocalDate"), ("total", "Double"), ("estado", "String")],
        "Producto": [("nombre", "String"), ("precio", "Double"), ("stock", "Integer")],
        "DetallePedido": [("cantidad", "Integer"), ("subtotal", "Double")],
        "Factura": [("numero", "Integer"), ("fechaEmision", "LocalDate"), ("montoTotal", "Double")],
        "Pago": [("monto", "Double"), ("fecha", "LocalDate"), ("metodo", "String")],
    },
    "universidad": {
        "Estudiante": [("nombre", "String"), ("registro", "String"), ("fechaNacimiento", "LocalDate")],
        "Docente": [("nombre", "String"), ("especialidad", "String"), ("email", "String")],
        "Materia": [("sigla", "String"), ("nombre", "String"), ("creditos", "Integer")],
        "Inscripcion": [("fecha", "LocalDate"), ("gestion", "String")],
        "Nota": [("valor", "Double"), ("aprobado", "Boolean")],
        "Carrera": [("nombre", "String"), ("codigo", "String")],
    },
    "clinica": {
        "Paciente": [("nombre", "String"), ("ci", "String"), ("fechaNacimiento", "LocalDate")],
        "Medico": [("nombre", "String"), ("matricula", "String"), ("especialidad", "String")],
        "Turno": [("fecha", "LocalDate"), ("hora", "String"), ("confirmado", "Boolean")],
        "HistoriaClinica": [("diagnostico", "String"), ("observaciones", "String")],
        "Receta": [("medicamento", "String"), ("dosis", "String")],
    },
    "biblioteca": {
        "Libro": [("titulo", "String"), ("isbn", "String"), ("anioPublicacion", "Integer")],
        "Autor": [("nombre", "String"), ("nacionalidad", "String")],
        "Socio": [("nombre", "String"), ("email", "String"), ("activo", "Boolean")],
        "Prestamo": [("fechaInicio", "LocalDate"), ("fechaDevolucion", "LocalDate"), ("devuelto", "Boolean")],
        "Ejemplar": [("codigo", "String"), ("disponible", "Boolean")],
    },
    "hotel": {
        "Huesped": [("nombre", "String"), ("documento", "String"), ("telefono", "String")],
        "Habitacion": [("numero", "Integer"), ("tipo", "String"), ("precioNoche", "Double")],
        "Reserva": [("fechaIngreso", "LocalDate"), ("fechaSalida", "LocalDate"), ("total", "Double")],
        "Servicio": [("nombre", "String"), ("costo", "Double")],
    },
}

# Relaciones "naturales" por dominio: (origen, destino, tipo, mult_origen, mult_destino, frase)
# Agregacion/composicion van de la PARTE al TODO (el rombo se dibuja en el
# destino), como el editor, el XMI y el generador de backend. Antes estaban
# al reves (todo -> parte) y el modelo aprendia composiciones invertidas.
RELATIONS = [
    ("Cliente", "Pedido", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("DetallePedido", "Pedido", "COMPOSITION", "1..*", "1", "como composición"),
    ("Producto", "DetallePedido", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Pedido", "Factura", "ASSOCIATION", "1", "1", "uno a uno"),
    ("Factura", "Pago", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Estudiante", "Inscripcion", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Materia", "Inscripcion", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Docente", "Materia", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Materia", "Carrera", "AGGREGATION", "1..*", "1", "como agregación"),
    ("Paciente", "Turno", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Medico", "Turno", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("HistoriaClinica", "Paciente", "COMPOSITION", "1", "1", "como composición"),
    ("Autor", "Libro", "ASSOCIATION", "1..*", "0..*", "de muchos a muchos"),
    ("Ejemplar", "Libro", "COMPOSITION", "1..*", "1", "como composición"),
    ("Socio", "Prestamo", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Huesped", "Reserva", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
    ("Habitacion", "Reserva", "ASSOCIATION", "1", "0..*", "de uno a muchos"),
]

INHERITANCE = [("Persona", "Estudiante"), ("Persona", "Docente"), ("Persona", "Paciente"),
               ("Persona", "Medico"), ("Usuario", "Socio"), ("Pago", "PagoTarjeta"), ("Pago", "PagoEfectivo")]

METHODS = [("calcularTotal", "Double"), ("confirmar", "void"), ("cancelar", "void"),
           ("estaVigente", "Boolean"), ("aplicarDescuento", "void"), ("generarResumen", "String")]

# Verbos de pedido en voseo (como habla el equipo) y en tuteo/neutro.
CREATE = ["creá", "crea", "agregá", "necesito", "haceme", "armá"]
ADD = ["agregale", "agrégale", "ponele", "añadile", "sumale"]
TYPE_WORDS = {"String": ["texto", "string"], "Integer": ["entero", "int"], "Double": ["decimal", "double"],
              "LocalDate": ["fecha", "date"], "Boolean": ["booleano", "boolean"]}


def first(name: str) -> str:
    return name.split()[0]


def act(tool: str, **args) -> dict:
    return {"tool": tool, "args": args}


def join_es(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


# ---------------------------------------------------------------------------
# Contextos (diagrama + equipo + hilo)
# ---------------------------------------------------------------------------
def diagram_of(classes: dict[str, list[tuple[str, str]]], rels: list[tuple] = ()) -> dict:
    return {
        "clases": [
            {"nombre": c, "atributos": [{"nombre": n, "tipo": t, "requerido": False} for n, t in attrs], "metodos": []}
            for c, attrs in classes.items()
        ],
        # Las relaciones con multiplicidades (tuplas de RELATIONS) las muestran
        # en el prompt, como el diagrama real (segundo parcial).
        "relaciones": [
            {"origen": r[0], "destino": r[1], "tipo": r[2], "etiqueta": None,
             **({"mult_origen": r[3], "mult_destino": r[4]} if len(r) >= 5 else {})}
            for r in rels
        ],
    }


def ctx(rng, who, question, classes=None, rels=(), team=None, history=None, solutions=False) -> dict:
    return {
        "requester_name": who,
        "question": question,
        "solutions_enabled": solutions,
        "diagram": diagram_of(classes or {}, rels),
        "team_context": team or [],
        "history": history or [],
    }


def random_team(rng, who, n=None) -> list[dict]:
    others = [p for p in PEOPLE if p != who]
    lines = [
        "¿arrancamos por las entidades principales?", "yo me encargo de las relaciones",
        "revisemos las multiplicidades antes de exportar", "dale, me parece bien",
        "falta definir los tipos de los atributos", "después exportamos el backend",
    ]
    return [{"author": rng.choice(others), "content": rng.choice(lines), "is_ai": False, "addressed_to": None}
            for _ in range(n if n is not None else rng.choice([0, 0, 1, 2]))]


def partial_diagram(rng, domain: str, k: int | None = None) -> dict[str, list]:
    classes = DOMAINS[domain]
    names = rng.sample(list(classes), k if k is not None else rng.randint(0, min(3, len(classes))))
    return {c: rng.sample(classes[c], rng.randint(0, len(classes[c]))) for c in names}


# ---------------------------------------------------------------------------
# 1. Ediciones por plantilla
# ---------------------------------------------------------------------------
def gen_edits(rng, n: int) -> list[tuple[dict, str]]:
    out = []
    for _ in range(n):
        who = rng.choice(PEOPLE)
        fn = first(who)
        domain = rng.choice(list(DOMAINS))
        existing = partial_diagram(rng, domain)
        kind = rng.choices(["class_attrs", "class", "attr", "attr_typed", "relation", "inherit",
                            "method", "rename", "delete_attr", "delete_class"],
                           weights=[22, 8, 14, 8, 16, 6, 6, 6, 7, 7])[0]
        free = [c for c in DOMAINS[domain] if c not in existing]

        if kind in ("class_attrs", "class") and free:
            cls = rng.choice(free)
            attrs = rng.sample(DOMAINS[domain][cls], rng.randint(1, len(DOMAINS[domain][cls]))) if kind == "class_attrs" else []
            q = f"{rng.choice(CREATE)} la clase {cls}"
            if attrs:
                q += f" con {join_es([a for a, _ in attrs])}"
            actions = [act("create_class", name=cls)] + [
                act("add_attribute", class_name=cls, name=a, type=t, required=False) for a, t in attrs]
            say = f"{fn}, creé la clase {cls}" + (f" con {join_es([f'{a} ({t})' for a, t in attrs])}." if attrs else ".")
        elif kind in ("attr", "attr_typed") and existing:
            cls = rng.choice(list(existing))
            options = [a for a in DOMAINS[domain][cls] if a not in existing[cls]] or DOMAINS[domain][cls]
            a, t = rng.choice(options)
            if kind == "attr_typed":
                q = f"{rng.choice(ADD)} a {cls} el atributo {a} de tipo {rng.choice(TYPE_WORDS[t])}"
            else:
                q = f"{rng.choice(ADD)} {a} a {cls}"
            actions = [act("add_attribute", class_name=cls, name=a, type=t, required=False)]
            say = f"{fn}, agregué el atributo {a} ({t}) a {cls}."
        elif kind == "relation":
            cands = [r for r in RELATIONS if r[0] in DOMAINS[domain] and r[1] in DOMAINS[domain]]
            o, d, t, mo, md, frase = rng.choice(cands)
            existing.setdefault(o, [])
            existing.setdefault(d, [])
            verb = rng.choice(["relacioná", "relaciona", "conectá", "uní"])
            q = f"{verb} {o} y {d} {frase}"
            actions = [act("create_relation", from_class=o, to_class=d, type=t, src_multiplicity=mo, dst_multiplicity=md)]
            tipo = {"ASSOCIATION": "una asociación", "COMPOSITION": "una composición",
                    "AGGREGATION": "una agregación"}[t]
            say = f"{fn}, creé {tipo} entre {o} ({mo}) y {d} ({md})."
        elif kind == "inherit":
            parent, child = rng.choice(INHERITANCE)
            existing = {parent: [("nombre", "String")], child: []}
            q = f"hacé que {child} herede de {parent}"
            actions = [act("create_relation", from_class=child, to_class=parent, type="INHERITANCE",
                           src_multiplicity="1", dst_multiplicity="1")]
            say = f"{fn}, ahora {child} hereda de {parent} (generalización)."
        elif kind == "method" and existing:
            cls = rng.choice(list(existing))
            m, rt = rng.choice(METHODS)
            q = f"{rng.choice(ADD)} a {cls} el método {m}" + (f" que devuelva {rt}" if rt != "void" else "")
            actions = [act("add_method", class_name=cls, name=m, return_type=rt)]
            say = f"{fn}, agregué el método {m}(): {rt} a {cls}."
        elif kind == "rename" and existing:
            cls = rng.choice(list(existing))
            new = rng.choice([cls + "s", "Registro" + cls, cls + "Entity", "Nuevo" + cls])
            q = f"renombrá {cls} a {new}"
            actions = [act("rename_class", class_name=cls, new_name=new)]
            say = f"{fn}, renombré la clase {cls} a {new}."
        elif kind == "delete_attr" and existing and any(existing.values()):
            cls = rng.choice([c for c in existing if existing[c]])
            a, _ = rng.choice(existing[cls])
            q = f"{rng.choice(['borrá', 'eliminá', 'sacale'])} el atributo {a} de {cls}"
            actions = [act("delete_attribute", class_name=cls, attribute_name=a)]
            say = f"{fn}, eliminé el atributo {a} de {cls}."
        elif kind == "delete_class" and existing:
            cls = rng.choice(list(existing))
            q = f"{rng.choice(['borrá', 'eliminá'])} la clase {cls}"
            actions = [act("delete_class", class_name=cls)]
            say = f"{fn}, eliminé la clase {cls}."
        else:
            continue
        out.append((ctx(rng, who, q, existing, team=random_team(rng, who)), pc.assistant_json(say, actions)))
    return out


# ---------------------------------------------------------------------------
# 2. Hilo individual: referencias a consultas previas de la misma persona
# ---------------------------------------------------------------------------
def gen_history_refs(rng, n: int) -> list[tuple[dict, str]]:
    out = []
    for _ in range(n):
        who = rng.choice(PEOPLE)
        fn = first(who)
        domain = rng.choice(list(DOMAINS))
        cls = rng.choice(list(DOMAINS[domain]))
        (a1, t1), (a2, t2) = rng.sample(DOMAINS[domain][cls], 2) if len(DOMAINS[domain][cls]) > 1 else (DOMAINS[domain][cls][0],) * 2
        history = [{"question": f"creá la clase {cls} con {a1}", "answer": f"{fn}, creé la clase {cls} con {a1} ({t1})."}]
        # Otro compañero estuvo trabajando con OTRA clase: la referencia es al hilo propio.
        other_cls = rng.choice([c for c in DOMAINS[domain] if c != cls])
        mate = rng.choice([p for p in PEOPLE if p != who])
        team = [{"author": mate, "content": f"(le pregunto a la IA) creá la clase {other_cls}",
                 "is_ai": False, "addressed_to": None},
                {"author": "Asistente IA", "content": f"{first(mate)}, creé la clase {other_cls}.", "is_ai": True,
                 "addressed_to": mate}]
        q = rng.choice([f"agregale también {a2}", f"y ponele {a2}", f"a esa clase sumale {a2}"])
        out.append((ctx(rng, who, q, {cls: [(a1, t1)], other_cls: []}, team=team, history=history),
                    pc.assistant_json(f"{fn}, agregué {a2} ({t2}) a {cls}.",
                                      [act("add_attribute", class_name=cls, name=a2, type=t2, required=False)])))
    return out


# ---------------------------------------------------------------------------
# 3. Entrega de soluciones según la configuración del diagrama
# ---------------------------------------------------------------------------
SOLUTION_ASKS = ["armame el diagrama de {d}", "diseñá el sistema de {d}", "haceme todo el modelo para {d}",
                 "proponé y construí las clases de {d}"]
SYSTEMS = {"una veterinaria": "veterinaria", "un colegio": "colegio", "una biblioteca": "biblioteca",
           "un hotel": "hotel", "una tienda online": "tienda online", "un gimnasio": "gimnasio",
           "una clínica": "clínica", "un cine": "cine", "un restaurante": "restaurante",
           "una agencia de viajes": "agencia de viajes", "un taller mecánico": "taller mecánico",
           "un banco": "banco", "un estacionamiento": "estacionamiento", "una farmacia": "farmacia",
           "una universidad": "universidad", "un sistema de turnos médicos": "turnos médicos",
           "una empresa de delivery": "delivery", "un torneo de fútbol": "torneo de fútbol",
           "una inmobiliaria": "inmobiliaria", "un sistema de encuestas": "encuestas"}


def _relation_action(r: dict) -> dict:
    """Relacion del maestro -> accion. Gemini describio agregacion/composicion
    del TODO a la PARTE (Pedido -> ItemPedido); el editor las dibuja de la
    parte al todo (rombo en el destino), asi que se invierten con sus
    multiplicidades."""
    src, dst, ms, md = r["from"], r["to"], r.get("src", "1"), r.get("dst", "0..*")
    if r["type"] in ("AGGREGATION", "COMPOSITION"):
        src, dst, ms, md = dst, src, md, ms
    return act("create_relation", from_class=src, to_class=dst, type=r["type"],
               src_multiplicity=ms, dst_multiplicity=md)


def gen_solutions(rng, teacher: list[dict]) -> list[tuple[dict, str]]:
    out = []
    by_system = {t["system"]: t for t in teacher}
    for system in SYSTEMS:
        for enabled in (False, True):
            for _ in range(2):
                who = rng.choice(PEOPLE)
                fn = first(who)
                q = rng.choice(SOLUTION_ASKS).format(d=system)
                if not enabled:
                    concepts = by_system.get(system, {}).get("classes", [])[:3]
                    hint = f" Suelen aparecer conceptos como {join_es([c['name'] for c in concepts])}." if concepts else ""
                    say = (f"{fn}, en este diagrama la entrega de soluciones está desactivada, así que no voy a "
                           f"armar el modelo completo.{hint} Decime qué clases querés crear y las vamos "
                           f"construyendo; el dueño del diagrama puede habilitar que entregue soluciones.")
                    out.append((ctx(rng, who, q, {}, team=random_team(rng, who), solutions=False), pc.assistant_json(say)))
                elif system in by_system:
                    t = by_system[system]
                    actions = []
                    for c in t["classes"]:
                        actions.append(act("create_class", name=c["name"]))
                        actions += [act("add_attribute", class_name=c["name"], name=a["name"], type=a["type"], required=False)
                                    for a in c.get("attributes", [])]
                    actions += [_relation_action(r) for r in t.get("relations", [])]
                    say = f"{fn}, {t['summary'][0].lower() + t['summary'][1:]}"
                    out.append((ctx(rng, who, q, {}, team=random_team(rng, who), solutions=True), pc.assistant_json(say, actions)))
    return out


# ---------------------------------------------------------------------------
# 4. Mentoría (destilada del maestro) con nombre y, a veces, el diagrama
# ---------------------------------------------------------------------------
def gen_mentor(rng, teacher: list[dict], per_question: int) -> list[tuple[dict, str]]:
    out = []
    for t in teacher:
        for _ in range(per_question):
            who = rng.choice(PEOPLE)
            fn = first(who)
            domain = rng.choice(list(DOMAINS))
            q = t["question"]
            if rng.random() < 0.3:
                q = "@IA " + q  # a veces queda la mención en el texto
            say = t["answer"].replace("{nombre}", fn)
            out.append((ctx(rng, who, q, partial_diagram(rng, domain), team=random_team(rng, who)),
                        pc.assistant_json(say)))
    return out


# ---------------------------------------------------------------------------
# Maestro (Gemini)
# ---------------------------------------------------------------------------
TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "gemini-3.5-flash")

MENTOR_INSTRUCTIONS = """Sos un mentor de diseño de software (UML, ingeniería de software, \
patrones, requerimientos) para estudiantes universitarios de Bolivia. Respondé la pregunta \
en español, de forma pedagógica y clara, en 2 a 6 líneas: definición corta, por qué importa y \
un ejemplo concreto (idealmente con clases de un sistema de ventas, universidad, clínica o \
biblioteca). Empezá EXACTAMENTE con "{nombre}, " (literal, con llaves). Texto plano: podés usar \
listas con guiones y **negrita** para un término, sin títulos ni tablas. Ortografía correcta."""

SOLUTION_INSTRUCTIONS = """Diseñá un diagrama de clases UML ACOTADO (3 a 6 clases) para el \
sistema indicado, como lo haría un desarrollador senior. Devolvé SOLO JSON con esta forma:
{"classes": [{"name": "PascalCase", "attributes": [{"name": "camelCase", "type": "String|Integer|Double|LocalDate|Boolean"}]}],
 "relations": [{"from": "Clase", "to": "Clase", "type": "ASSOCIATION|AGGREGATION|COMPOSITION|INHERITANCE|DEPENDENCY", "src": "1", "dst": "0..*"}],
 "summary": "Una o dos oraciones en español, en primera persona, resumiendo lo que construiste y la decisión clave."}
Cada clase con 2 a 4 atributos. Nombres sin tildes ni espacios."""


def _client():
    from google import genai
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Falta GEMINI_API_KEY para generar las respuestas del maestro.")
    return genai.Client(api_key=key)


FALLBACK_TEACHER = os.environ.get("FALLBACK_TEACHER_MODEL", "gemini-3.5-flash-lite")
_teacher = {"model": TEACHER_MODEL}


def _ask(client, prompt: str, json_mode: bool = False) -> str:
    from google.genai import types
    cfg = types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json" if json_mode else None)
    for attempt in range(5):
        try:
            return client.models.generate_content(model=_teacher["model"], contents=prompt, config=cfg).text
        except Exception as e:
            quota = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
            if quota and _teacher["model"] != FALLBACK_TEACHER:
                # Cuota diaria agotada del maestro principal: se sigue con el de respaldo.
                print(f"  cuota agotada en {_teacher['model']}: sigo con {FALLBACK_TEACHER}", file=sys.stderr)
                _teacher["model"] = FALLBACK_TEACHER
                continue
            wait = 5 * (attempt + 1)
            print(f"  reintento en {wait}s ({type(e).__name__})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("El maestro no respondió")


def run_teacher() -> None:
    client = _client()
    questions = [l.strip() for l in (DATA / "mentor_questions.txt").read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    done = {json.loads(l)["question"] for l in TEACHER_MENTOR.read_text(encoding="utf-8").splitlines()} \
        if TEACHER_MENTOR.exists() else set()
    with TEACHER_MENTOR.open("a", encoding="utf-8") as f:
        for i, q in enumerate(questions, 1):
            if q in done:
                continue
            ans = _ask(client, f"{MENTOR_INSTRUCTIONS}\n\nPregunta: {q}").strip()
            if not ans.startswith("{nombre}"):
                ans = "{nombre}, " + ans
            f.write(json.dumps({"question": q, "answer": ans, "teacher": _teacher["model"]}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[mentor {i}/{len(questions)}] {q}")
    done = {json.loads(l)["system"] for l in TEACHER_SOLUTIONS.read_text(encoding="utf-8").splitlines()} \
        if TEACHER_SOLUTIONS.exists() else set()
    with TEACHER_SOLUTIONS.open("a", encoding="utf-8") as f:
        for system in SYSTEMS:
            if system in done:
                continue
            raw = _ask(client, f"{SOLUTION_INSTRUCTIONS}\n\nSistema: {system}", json_mode=True)
            data = json.loads(raw)
            data["system"] = system
            data["teacher"] = _teacher["model"]
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[solución] {system}: {[c['name'] for c in data['classes']]}")


# ---------------------------------------------------------------------------
# 5. Revision del diagrama con PROPUESTA (segundo parcial)
# ---------------------------------------------------------------------------
# El asesor explica el diagnostico y deja en "actions" los cambios que
# propone; la app los muestra como propuesta y un integrante los acepta. Si
# el diagrama ya esta bien, no propone nada (evita proponer por proponer).
REVIEW_REL_ASKS = [
    "¿cómo relacionamos {a} y {b}?", "¿qué relación debería haber entre {a} y {b}?",
    "¿cómo conectamos {a} con {b}?", "revisá cómo se relacionan {a} y {b}",
    "¿{a} y {b} deberían estar relacionadas?",
]
REVIEW_MULT_ASKS = [
    "revisá la relación entre {a} y {b}, ¿está bien la cardinalidad?",
    "¿está bien la multiplicidad entre {a} y {b}?", "¿es correcta la relación de {a} con {b}?",
    "revisá la cardinalidad de {a} y {b}",
]
REVIEW_ATTR_ASKS = ["¿qué atributos le faltan a {a}?", "¿qué le falta a la clase {a}?",
                    "revisá la clase {a}, ¿le falta algo?", "¿{a} está completa?"]
WHY = {
    ("1", "0..*"): "un {a} puede tener varios {b} y cada {b} pertenece a un solo {a}",
    ("1", "1..*"): "un {a} tiene al menos un {b} y cada {b} pertenece a un solo {a}",
    ("1..*", "1"): "{a} es parte de {b}: cada {b} tiene uno o más {a} y cada {a} pertenece a un solo {b}",
    ("1..*", "0..*"): "un {a} puede estar en varios {b} y cada {b} tiene uno o más {a}",
    ("1", "1"): "cada {a} se corresponde con exactamente un {b}",
}
REL_ES = {"ASSOCIATION": "asociación", "AGGREGATION": "agregación", "COMPOSITION": "composición"}
PROPOSE = ["Te lo dejo propuesto para que el equipo lo revise.",
           "Lo dejo como propuesta para que lo apliquen si están de acuerdo.",
           "Quedó propuesto: lo pueden aplicar desde el chat."]


def _mult_text(mo: str, md: str) -> str:
    return f"{mo} → {md}"


def gen_reviews(rng, n: int) -> list[tuple[dict, str]]:
    out = []
    domain_of = {c: d for d, classes in DOMAINS.items() for c in classes}
    rels = [r for r in RELATIONS if r[0] in domain_of and domain_of[r[0]] == domain_of.get(r[1])]
    for _ in range(n):
        who = rng.choice(PEOPLE)
        fn = first(who)
        o, d, t, mo, md, _frase = rng.choice(rels)
        dom = DOMAINS[domain_of[o]]
        classes = {c: rng.sample(dom[c], rng.randint(1, len(dom[c]))) for c in (o, d)}
        why = WHY.get((mo, md), "es la cardinalidad que corresponde a este dominio").format(a=o, b=d)
        kind = rng.choices(["missing_rel", "wrong_mult", "ok_rel", "missing_attr"], weights=[35, 25, 15, 25])[0]

        if kind == "missing_rel":
            q = rng.choice(REVIEW_REL_ASKS).format(a=o, b=d)
            say = (f"{fn}, hoy {o} y {d} no están relacionadas. Conviene una {REL_ES.get(t, t.lower())} "
                   f"{o} {_mult_text(mo, md)} {d}: {why}. {rng.choice(PROPOSE)}")
            actions = [act("create_relation", from_class=o, to_class=d, type=t,
                           src_multiplicity=mo, dst_multiplicity=md)]
            out.append((ctx(rng, who, q, classes, team=random_team(rng, who)), pc.assistant_json(say, actions)))
        elif kind == "wrong_mult":
            wrong = rng.choice([w for w in (("1", "1"), ("0..*", "1"), ("1", "0..1")) if w != (mo, md)])
            q = rng.choice(REVIEW_MULT_ASKS).format(a=o, b=d)
            say = (f"{fn}, la relación {o} {_mult_text(*wrong)} {d} no es correcta: {why}, así que "
                   f"debería ser {_mult_text(mo, md)}. Propongo reemplazarla. {rng.choice(PROPOSE)}")
            actions = [act("delete_relation", from_class=o, to_class=d),
                       act("create_relation", from_class=o, to_class=d, type=t,
                           src_multiplicity=mo, dst_multiplicity=md)]
            rel = [(o, d, t, wrong[0], wrong[1])]
            out.append((ctx(rng, who, q, classes, rel, team=random_team(rng, who)), pc.assistant_json(say, actions)))
        elif kind == "ok_rel":
            q = rng.choice(REVIEW_MULT_ASKS).format(a=o, b=d)
            say = (f"{fn}, la relación {o} {_mult_text(mo, md)} {d} está bien: {why}. "
                   f"No hace falta cambiarla.")
            out.append((ctx(rng, who, q, classes, [(o, d, t, mo, md)], team=random_team(rng, who)),
                        pc.assistant_json(say, [])))
        else:
            target = rng.choice([o, d])
            have = rng.sample(dom[target], rng.randint(0, max(0, len(dom[target]) - 2)))
            missing = [a for a in dom[target] if a not in have][:3]
            classes[target] = have
            q = rng.choice(REVIEW_ATTR_ASKS).format(a=target)
            listed = join_es([f"{n_} ({t_})" for n_, t_ in missing])
            say = (f"{fn}, a {target} le faltan datos básicos para el dominio: {listed}. "
                   f"{rng.choice(PROPOSE)}")
            actions = [act("add_attribute", class_name=target, name=n_, type=t_, required=False) for n_, t_ in missing]
            out.append((ctx(rng, who, q, classes, team=random_team(rng, who)), pc.assistant_json(say, actions)))
    return out


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Armado final
# ---------------------------------------------------------------------------
def to_example(context: dict, answer: str, system: str) -> dict:
    """Formato "messages" (lo usa el notebook con el chat template de Gemma).
    El prompt de sistema va dentro del turno de usuario, igual que en la app."""
    return {"messages": [
        {"role": "user", "content": f"{system}\n\n{pc.build_user_message(context)}"},
        {"role": "assistant", "content": answer},
    ]}


def build(seed: int = 42, eval_ratio: float = 0.08) -> dict:
    rng = random.Random(seed)
    system = pc.system_prompt()
    mentor = _load(TEACHER_MENTOR)
    solutions = _load(TEACHER_SOLUTIONS)
    if not mentor:
        print("AVISO: no hay respuestas de mentoría del maestro (correr con --teacher).", file=sys.stderr)

    pairs = []
    pairs += gen_edits(rng, 700)
    pairs += gen_history_refs(rng, 160)
    pairs += gen_mentor(rng, mentor, per_question=4)
    pairs += gen_solutions(rng, solutions)
    pairs += gen_reviews(rng, 260)
    rng.shuffle(pairs)

    examples = [to_example(c, a, system) for c, a in pairs]
    n_eval = max(1, int(len(examples) * eval_ratio))
    DATA.mkdir(exist_ok=True)
    for name, rows in (("eval.jsonl", examples[:n_eval]), ("train.jsonl", examples[n_eval:])):
        with (DATA / name).open("w", encoding="utf-8", newline="\n") as f:  # LF tambien en Windows
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {"train": len(examples) - n_eval, "eval": n_eval, "mentor_teacher": len(mentor),
             "solutions_teacher": len(solutions)}
    print(json.dumps(stats))
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--teacher", action="store_true", help="generar/completar las respuestas del maestro (Gemini)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.teacher:
        run_teacher()
    build(seed=args.seed)
