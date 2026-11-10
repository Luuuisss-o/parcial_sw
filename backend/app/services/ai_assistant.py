# app/services/ai_assistant.py
"""
Asistente de IA que edita el diagrama UML por comandos de texto/voz.

Regla de la catedra (no negociable): el asistente NUNCA genera el diagrama
completo a partir de un problema descrito. Solo ejecuta ediciones puntuales
sobre lo que el usuario le va pidiendo, una instruccion a la vez, usando las
tools de ai_tools.py -- las mismas operaciones que ya expone la API REST.

Flujo: texto del usuario -> Gemini decide que tool(s) llamar -> se ejecutan
contra la base de datos -> se le devuelve el resultado a Gemini -> Gemini
responde en lenguaje natural confirmando lo que hizo (o explicando por que
no pudo). El flujo web es sincrono: la voz se transcribe en el cliente (Web
Speech API) y llega aca ya como texto.

Usa Google Gemini (google-genai) en vez de un proveedor de pago: el
enunciado no exige un proveedor de IA en particular para el editor, y
Gemini tiene capa gratuita sin tarjeta.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from google import genai  # noqa: F401  (los tests reemplazan genai.Client)

from app.core.config import settings
from app.models.uml import Diagram
from app.services import llm_providers
from app.services import ai_proposals
from app.services.ai_tools import CONFIRM_RE, DiagramToolExecutor, ToolError, TOOLS, as_gemini_tools

logger = logging.getLogger(__name__)

MODEL = llm_providers.DEFAULT_GEMINI_MODEL
MAX_TOOL_TURNS = 6  # tope de vueltas del loop para evitar bucles infinitos
# Con la entrega de soluciones activada una respuesta puede crear varias
# clases, atributos y relaciones encadenados: se permiten mas vueltas.
MAX_TOOL_TURNS_SOLUTIONS = 15

INSIST_ON_TOOLS = (
    "No ejecutaste ninguna herramienta, asi que el diagrama NO cambio. Si el "
    "pedido requiere crear, modificar o eliminar algo, llama ahora a las "
    "herramientas necesarias. No confirmes cambios que no ejecutaste."
)
NO_CHANGES_REPLY = (
    "No apliqué ningún cambio en el diagrama: no logré ejecutar ese pedido. "
    "¿Podés repetirlo o reformularlo?"
)

MODE_AUTO = "AUTO"      # el modelo decide: explicar, editar o ambas
MODE_MENTOR = "MENTOR"  # consulta teorica: sin herramientas, no toca el diagrama

# --- Clasificacion de intencion (determinista, sin llamar al modelo) ---------
# Una consulta "claramente teorica" (empieza preguntando que es / como / por
# que..., o pide explicar/definir) y SIN verbos de edicion se responde en modo
# mentor: el modelo no recibe herramientas, asi que no puede modificar el
# diagrama aunque se equivoque. Todo lo demas va en modo AUTO, donde el
# modelo puede explicar y/o editar.
_THEORY_RE = re.compile(
    r"^\s*[¿¡]?\s*(?:"
    r"qu[eé]|cu[aá]l(?:es)?|c[oó]mo|por\s*qu[eé]|para\s+qu[eé]|cu[aá]ndo|d[oó]nde|"
    r"en\s+qu[eé]|es\s+(?:correcto|mejor|buena|bueno|necesario|v[aá]lido)|"
    r"conviene|deber[ií]a|se\s+puede|puedo|"
    r"expl[ií]ca(?:me|nos|melo|mela|noslo)?|explic[aá](?:me|nos|melo|mela|noslo)?|"
    r"defin[ei]|define|describ[ei]|"
    r"diferencia|ejemplo|dame\s+un\s+ejemplo|ens[eé][nñ]a(?:me|nos)?|"
    r"what|why|how|explain"
    r")\b",
    re.IGNORECASE,
)
# Verbos de edicion (infinitivo, imperativo tu/vos con o sin pronombre
# enclitico, y presente voseante "agregás"). Si aparece alguno, la consulta
# puede pedir un cambio y se usa el modo AUTO.
_EDIT_STEMS = (
    "cre", "agreg", "elimin", "borr", "quit", "renombr", "cambi", "relacion",
    "conect", "aplic", "modific", "gener", "asoci", "vincul", "insert",
)
_EDIT_RE = re.compile(
    r"\b(?:"
    r"(?:" + "|".join(_EDIT_STEMS) + r")(?:[aá]r|[aá]s|[aá](?:me|le|les|la|las|lo|los|melo|selo)?)|"
    r"a[nñ]ad[ei](?:r|le|s)?|a[nñ]ad[ií]s|"
    r"pon[eé](?:le|les|r|s|la|lo)?|ponle|"
    r"un[ií](?:r|los|las|s)|mov[eé](?:r|la|lo|s)?|"
    r"hac[eé](?:la|lo|me|s)|hacela|"
    r"create|add|delete|remove|rename"
    r")\b",
    re.IGNORECASE,
)


# Dudas en primera persona ("no me acuerdo que es un atributo derivado",
# ejemplo literal del docente): son consultas teoricas aunque no lleven "?".
_DOUBT_RE = re.compile(
    r"\b(?:no\s+me\s+acuerdo|no\s+recuerdo|no\s+entiendo|no\s+s[eé]\s+(?:qu[eé]|c[oó]mo|cu[aá]l|si)|"
    r"tengo\s+(?:una\s+)?duda|me\s+olvid[eé]|me\s+confunde|no\s+me\s+queda\s+claro)\b",
    re.IGNORECASE,
)


def classify_intent(text: str) -> str:
    """MODE_MENTOR si la consulta es claramente teorica, MODE_AUTO si no.

    Teorica = empieza como pregunta/pedido de explicacion, o es una pregunta
    (lleva "?"), y en ningun caso contiene un verbo de edicion."""
    if _EDIT_RE.search(text):
        return MODE_AUTO
    if _THEORY_RE.search(text) or _DOUBT_RE.search(text) or "?" in text:
        return MODE_MENTOR
    return MODE_AUTO

SYSTEM_PROMPT = """Sos un integrante mas del equipo que disena un diagrama \
de clases UML en un editor colaborativo: actuas como desarrollador senior y \
moderador del grupo. Los demas integrantes trabajan desde lugares distintos, \
cada uno con su sesion, sobre el mismo tablero, y te hablan por el chat del \
equipo. Cumplis DOS roles:

ROL 1 - MENTOR DE DISENO DE SOFTWARE
Respondes dudas teoricas y de diseno de ingenieria de software: UML \
(tipos de relacion, multiplicidad, clases de asociacion, herencia vs \
composicion), patrones de diseno, principios (SOLID, cohesion, \
acoplamiento), requerimientos (funcionales, no funcionales, delegados, \
casos de uso), arquitectura, persistencia, metodologias (PUDS/RUP), etc.
Como mentor:
- Explica de forma pedagogica y clara, para estudiantes: una definicion \
  corta, por que importa y un ejemplo concreto. Si el diagrama actual \
  sirve de ejemplo, usalo ("en su diagrama, Pedido y DetallePedido...").
- Una pregunta teorica NO modifica el diagrama: no llames herramientas \
  para responderla. Si ves algo mejorable en el diagrama, sugerilo en \
  texto y deja que el equipo decida si lo pide.
- Extension: entre 3 y 10 lineas.
- Si la pregunta no tiene nada que ver con ingenieria de software, \
  redirigi amablemente al tema del proyecto.

ROL 2 - EJECUTOR DE EDICIONES DEL DIAGRAMA
Cuando te piden un cambio concreto, lo ejecutas llamando a las herramientas.
1. Ejecuta SIEMPRE lo que el usuario pide, usando las herramientas. Si el \
   pedido nombra los elementos concretos, hacelo sin pedir confirmacion ni \
   pedir que te lo repitan paso a paso. UNICA excepcion: si una herramienta \
   responde CONFIRMACION REQUERIDA (borrar una clase con contenido o varias \
   cosas a la vez), no reintentes: explica en una linea que se perderia y \
   pedile que confirme con "@IA confirmo, ...".
2. Un solo mensaje puede implicar VARIAS herramientas, y esta perfecto \
   encadenarlas. Ejemplos que SI debes ejecutar completos:
   - "crea la clase Usuario y agregale nombre, ci, contrasena y correo" \
     -> create_class(Usuario) + 4 add_attribute.
   - "crea Cliente y Pedido y relacionalos de uno a muchos" \
     -> 2 create_class + create_relation.
   - "a Factura ponele total decimal y fecha date" -> 2 add_attribute.
3. Si el usuario no aclara el tipo de un atributo, elegi vos el tipo mas \
   razonable (String para nombres/correos/textos, Integer para cantidades, \
   Double para montos, LocalDate para fechas, Boolean para si/no) y segui.
4. Si el usuario no aclara el tipo de una relacion, usa ASSOCIATION.
{solutions_rule}6. Al terminar, confirma en una o dos lineas exactamente que ejecutaste. \
   Nunca inventes cambios que no hiciste. Si una herramienta devuelve \
   error, leelo y corregi si podes; si no, explica que paso.
Un mensaje puede mezclar ambos roles ("que es una composicion? aplicala \
entre Pedido y Detalle"): ejecuta lo pedido y explica en pocas lineas (6 \
como maximo en total): la idea clave y por que la aplicaste asi.

FORMATO (el chat es angosto)
- Parrafos cortos. Podes usar listas con guiones, **negrita** para \
  resaltar un termino y `codigo` para nombres de clases/atributos/tipos.
- NO uses titulos (#, ##, ###), separadores (---), tablas ni emojis.
- Escribi con ortografia correcta del español (tildes y eñe: "diseño", \
  "construí", "relación"), aunque estas instrucciones no las lleven.

CHAT GRUPAL Y MEMORIA
- Varios colaboradores te escriben y TODOS ven tus respuestas. En cada \
  consulta se te indica QUIEN te esta preguntando (nombre y email).
- Dirigite SIEMPRE a esa persona por su nombre de pila al empezar la \
  respuesta (ej: "Ana, una agregacion es..."). Nunca le respondas a otro \
  colaborador ni ejecutes el pedido de otra persona.
- Recibis tres niveles de contexto:
  a) el estado actual del diagrama (contexto global, siempre vigente);
  b) la conversacion reciente del equipo (contexto global: sirve para \
     entender de que se esta hablando, decisiones tomadas, o referencias \
     como "lo que propuso Bruno");
  c) el hilo de consultas previas de la persona que pregunta (su contexto \
     individual: resuelve referencias como "agregale otro atributo", \
     "explicamelo con otro ejemplo" o "esa clase").
  Responde SOLO a la consulta actual de quien pregunta, apoyandote en su \
  hilo individual y usando el contexto del equipo y del diagrama como \
  fondo. Si una referencia es ambigua entre lo que dijo la persona y lo \
  que dijo otro, prioriza el hilo de la persona.

Responde siempre en español.
"""

# Regla 5 del ROL 2, segun la configuracion del diagrama (la elige el dueño).
SOLUTIONS_RULE_OFF = """5. Entrega de soluciones DESACTIVADA en este diagrama: no disenies el \
   modelo completo por el usuario. Si te describen un problema de negocio \
   en general y te piden que vos decidas las clases ("armame el diagrama \
   de una veterinaria"), no lo construyas: como mentor podes orientar (que \
   preguntas hacerse, que conceptos suelen aparecer) y aclara que el dueño \
   del diagrama puede habilitar que entregues soluciones; pedile que te \
   indique que clases quiere crear. Un pedido que YA nombra clases, \
   atributos o relaciones concretas NO entra en esta restriccion: eso \
   ejecutalo siempre.
"""

SOLUTIONS_RULE_ON = """5. Entrega de soluciones ACTIVADA en este diagrama: si te piden una \
   solucion ("armame el diagrama de una veterinaria", "resolve la parte de \
   pagos", "proponé como modelar los turnos"), disenala y construila con \
   las herramientas como lo haria un desarrollador senior: clases con sus \
   atributos (tipos razonables) y relaciones con tipo y multiplicidad. \
   Integrala con lo que ya existe en el diagrama (no dupliques clases) y \
   respeta las decisiones que el equipo ya tomo en el chat. Mantene la \
   solucion acotada a lo pedido (tipicamente 3 a 8 clases). Al terminar, \
   resumi en pocas lineas que construiste y las decisiones clave, para que \
   el equipo pueda revisarlas y ajustarlas.
"""


def system_prompt(solutions_enabled: bool) -> str:
    rule = SOLUTIONS_RULE_ON if solutions_enabled else SOLUTIONS_RULE_OFF
    return SYSTEM_PROMPT.replace("{solutions_rule}", rule)


@dataclass
class Requester:
    """Quien le hace la consulta a la IA (CU-16)."""
    user_id: int | None
    name: str
    email: str | None = None


@dataclass
class AiCommandResult:
    reply: str
    actions: list[dict] = field(default_factory=list)
    mode: str = "AUTO"  # MODE_MENTOR si se respondio como mentor, sin herramientas
    model_label: str | None = None  # que modelo respondio (CU-17)
    # Propuesta del asesor (segundo parcial): {"summary", "operations",
    # "base_hash"} ya validada contra el diagrama; NO se aplico.
    proposal: dict | None = None
    revision: str | None = None  # revision del diagrama con la que se respondio


# Presupuesto de contexto: un diagrama mas grande que esto se manda en forma
# compacta (nombres y tipos, sin coordenadas) para no exceder el contexto.
MAX_STATE_CHARS = 30000


def compact_state(snapshot: dict) -> tuple[str, bool]:
    """JSON del diagrama para el prompt y si hubo que compactarlo."""
    full = json.dumps(snapshot, ensure_ascii=False)
    if len(full) <= MAX_STATE_CHARS:
        return full, False
    compact = {
        "clases": [
            {"nombre": c["nombre"],
             "atributos": [f"{a['nombre']}: {a['tipo']}" for a in c["atributos"]],
             "metodos": [m["nombre"] for m in c["metodos"]]}
            for c in snapshot["clases"]
        ],
        "relaciones": [
            f"{r['origen']} {r.get('mult_origen', '')} -[{r['tipo']}]-> {r['destino']} {r.get('mult_destino', '')}"
            for r in snapshot["relaciones"]
        ],
    }
    text = json.dumps(compact, ensure_ascii=False)
    if len(text) > MAX_STATE_CHARS:
        text = text[:MAX_STATE_CHARS] + " ...(truncado)"
    return text, True


def _describe(actions: list[dict]) -> str:
    """Resumen legible de lo que se alcanzo a ejecutar, para cuando el modelo
    no llega a redactar la confirmacion final (timeout / tope de pasos)."""
    if not actions:
        return ""
    partes = []
    for a in actions:
        r = a.get("result", {})
        if a["tool"] == "create_class":
            partes.append(f"clase {r.get('clase')}")
        elif a["tool"] == "add_attribute":
            partes.append(f"atributo {r.get('atributo')} en {r.get('clase')}")
        elif a["tool"] == "add_method":
            partes.append(f"metodo {r.get('metodo')} en {r.get('clase')}")
        elif a["tool"] == "create_relation":
            partes.append(f"relacion {r.get('origen')}-{r.get('destino')}")
        else:
            partes.append(a["tool"])
    return ", ".join(partes)


@dataclass
class TeamMessage:
    """Un mensaje de la conversacion reciente del equipo (contexto global)."""
    author: str
    content: str
    is_ai: bool = False
    addressed_to: str | None = None


def build_prompt(state_json: str, user_text: str, requester: Requester | None = None,
                 history: list[tuple[str, str]] | None = None,
                 team_context: list[TeamMessage] | None = None,
                 mode: str = "auto", proposals: bool = False, compacted: bool = False) -> str:
    """Arma el mensaje para el modelo con la memoria hibrida: quien pregunta,
    su hilo individual con la IA, la conversacion reciente del equipo y el
    estado actual del diagrama."""
    partes: list[str] = []
    if requester is not None:
        contacto = f" ({requester.email})" if requester.email else ""
        partes.append(f"Usuario que te consulta: {requester.name}{contacto}")

    partes.append(f"[Contexto global] Estado actual del diagrama (JSON):\n{state_json}")
    if compacted:
        partes.append("(El diagrama es grande: se envio en forma compacta, sin coordenadas.)")

    if team_context:
        lineas = ["[Contexto global] Conversacion reciente del equipo en el chat (de la mas vieja a la mas nueva):"]
        for m in team_context:
            if m.is_ai:
                destino = f" a {m.addressed_to}" if m.addressed_to else ""
                lineas.append(f"- Vos (IA) respondiste{destino}: {m.content}")
            else:
                lineas.append(f"- {m.author}: {m.content}")
        partes.append("\n".join(lineas))

    if requester is not None and history:
        lineas = [f"[Hilo individual] Consultas previas de {requester.name} a la IA (de la mas vieja a la mas nueva):"]
        for i, (pregunta, respuesta) in enumerate(history, 1):
            lineas.append(f"{i}. {requester.name} pregunto: {pregunta}")
            lineas.append(f"   Vos respondiste: {respuesta}")
        partes.append("\n".join(lineas))

    if mode == MODE_MENTOR:
        partes.append(
            "Esta consulta es teorica/conceptual o de revision: responde como mentor "
            "y desarrollador senior, sin modificar el diagrama. Explica tu diagnostico "
            "y recomendacion en texto. Si recomendas crear o cambiar algo concreto sobre "
            "clases REALES del diagrama (una relacion, una multiplicidad, un atributo "
            "faltante), SIEMPRE registralo ademas con la herramienta propose_changes: "
            "queda como PROPUESTA que el equipo acepta o rechaza con un boton. Nunca "
            "digas que aplicaste un cambio: como mucho, que lo dejaste propuesto."
            if proposals else
            "Esta consulta es teorica/conceptual: responde como mentor, sin "
            "modificar el diagrama (en este turno no tenes herramientas)."
        )
    quien = f" de {requester.name}" if requester is not None else " del usuario"
    partes.append(f"Consulta actual{quien} (respondele a esta):\n{user_text}")
    return "\n\n".join(partes)


def run_command(db, diagram: Diagram, user_text: str, requester: Requester | None = None,
                history: list[tuple[str, str]] | None = None,
                team_context: list[TeamMessage] | None = None,
                mode: str | None = None, solutions_enabled: bool = False,
                provider: llm_providers.ProviderConfig | None = None,
                proposals_enabled: bool = False) -> AiCommandResult:
    """Responde una consulta. `mode`:
      - MODE_MENTOR: pregunta teorica -> se llama al modelo SIN herramientas,
        asi es imposible que modifique el diagrama.
      - MODE_AUTO: el modelo decide (explicar, editar, o ambas).
    Si no se indica, se clasifica con classify_intent().

    `provider`: que modelo responde (Gemini, o uno local/OpenAI-compatible,
    ver llm_providers.py). Por defecto, el configurado para el diagrama."""
    mode = mode or classify_intent(user_text)
    cfg = provider or llm_providers.config_for(diagram)
    if cfg.kind == llm_providers.PROVIDER_TRAINED:
        from app.services import trained_model
        return trained_model.run(db, diagram, user_text, requester, history, team_context, mode,
                                 solutions_enabled, proposals_enabled, cfg.label)
    result = _run(db, diagram, user_text, requester, history, team_context, mode, solutions_enabled, cfg,
                  proposals_enabled=proposals_enabled)
    result.model_label = cfg.label
    return result


# El asesor dice que dejo una propuesta (sin haberla registrado).
_CLAIMS_PROPOSAL_RE = re.compile(
    r"(registr|dej)\w*\s+(\w+\s+){0,4}propuest|propuest\w*\s+(registrad|en el (tablero|panel|chat))",
    re.IGNORECASE,
)
INSIST_ON_PROPOSAL = (
    "Dijiste que dejaste una propuesta pero NO llamaste a propose_changes, asi que no "
    "quedo nada registrado. Si recomendas cambios concretos, llama ahora a "
    "propose_changes con las operaciones; si no, responde sin decir que quedo propuesta. "
    "El usuario no ve este aviso: no pidas disculpas ni lo menciones, responde a su pregunta."
)
NO_PROPOSAL_NOTE = ("\n\n_(Aclaración: esta vez no quedó registrada una propuesta aplicable. "
                    "Si querés que la deje propuesta, pedímelo de nuevo.)_")


def _advisor_reply(session, turn, snapshot: dict, _insisted: bool = False) -> tuple[str, dict | None]:
    """Turno del asesor: si llama a propose_changes, la propuesta se valida
    contra el diagrama (sin ejecutar nada). Si es invalida se le devuelven
    los errores UNA vez para que la corrija; si sigue invalida, se descarta
    (la respuesta en texto se publica igual)."""
    proposal = None
    first_text = (turn.text or "").strip()
    text = first_text
    for _ in range(2):
        if not turn.calls:
            break
        results = []
        for call in turn.calls:
            if call.name != "propose_changes" or proposal is not None:
                results.append((call, json.dumps({"error": "En este turno solo podes proponer (una vez)."})))
                continue
            ops, errors, touched = ai_proposals.validate_operations(snapshot, call.arguments.get("operations"))
            summary = str(call.arguments.get("summary") or "").strip()
            if errors or not summary:
                results.append((call, json.dumps(
                    {"error": "Propuesta invalida, corregila", "detalles": errors or ["Falta el resumen."]},
                    ensure_ascii=False)))
                continue
            proposal = {"summary": summary[:1000], "operations": ops,
                        "base_hash": ai_proposals.touched_hash(snapshot, touched)}
            results.append((call, json.dumps(
                {"ok": True, "registrada": True,
                 "nota": ("Quedo como propuesta pendiente; NO se aplico. Ahora responde en texto, "
                          "dirigiendote a quien pregunto: tu diagnostico del diagrama actual (que "
                          "falta o que esta mal, con las clases reales), la recomendacion y POR QUE "
                          "(multiplicidades, integridad), en 3 a 8 lineas, y aclara que quedo como "
                          "propuesta para que el equipo la revise y la acepte o rechace.")},
                ensure_ascii=False)))
        try:
            turn = session.send_tool_results(results)
        except Exception as e:
            logger.warning(f"[AI ADVISOR] corte tras proponer: {e}")
            break
        # La respuesta final ya trae la explicacion completa (se la pide la
        # nota del resultado); el texto previo queda solo si no hay final.
        text = (turn.text or "").strip() or text
    if proposal is None and _CLAIMS_PROPOSAL_RE.search(text or ""):
        if not _insisted:
            try:
                retry = session.insist_on_tools(INSIST_ON_PROPOSAL)
            except Exception as e:
                logger.warning(f"[AI ADVISOR] fallo al insistir con la propuesta: {e}")
                retry = None
            if retry is not None:
                retry_text, proposal = _advisor_reply(session, retry, snapshot, _insisted=True)
                if proposal is not None:
                    return retry_text or text, proposal
        # Nunca confirmar algo que no se hizo.
        text = (text or "") + NO_PROPOSAL_NOTE
    if proposal is not None and not text:
        text = "Te dejé una propuesta de cambios para revisar."
    if proposal is not None:
        # Anclar la respuesta al modelo real: si el texto no nombra ninguna de
        # las clases que toca la propuesta, se agrega el detalle de los cambios.
        names = {str(v) for op in proposal["operations"] for k, v in op["args"].items()
                 if k in ("class_name", "from_class", "to_class", "name", "new_name")}
        if not any(n and n.lower() in (text or "").lower() for n in names):
            cambios = "; ".join(ai_proposals.describe(op) for op in proposal["operations"])
            text = f"{text}\n\n**Propuesta:** {cambios}."
    return text, proposal


def _run(db, diagram, user_text, requester, history, team_context, mode, solutions_enabled,
         cfg: llm_providers.ProviderConfig, proposals_enabled: bool = False) -> AiCommandResult:
    session = llm_providers.open_session(cfg)  # valida la config antes de hacer nada
    # Eliminaciones con impacto (clase con contenido, varias a la vez) solo si
    # el usuario confirmo explicitamente en este mensaje (ver ai_tools).
    executor = DiagramToolExecutor(db, diagram, destructive_confirmed=bool(CONFIRM_RE.search(user_text)))

    snapshot = executor.snapshot()
    revision = ai_proposals.diagram_revision(snapshot)
    state, compacted = compact_state(snapshot)
    sys_prompt = system_prompt(solutions_enabled)
    advisor_tools = mode == MODE_MENTOR and proposals_enabled
    prompt = build_prompt(state, user_text, requester=requester, history=history,
                          team_context=team_context, mode=mode,
                          proposals=advisor_tools, compacted=compacted)

    actions: list[dict] = []

    # Primera llamada: si falla, no se ejecuto nada todavia y el error se
    # propaga para que el chat lo muestre. El asesor (MENTOR) solo recibe la
    # herramienta de PROPONER: no tiene ninguna que modifique el diagrama.
    if mode == MODE_MENTOR:
        tools = as_gemini_tools([ai_proposals.PROPOSE_TOOL]) if advisor_tools else None
    else:
        tools = TOOLS
    turn = session.start(sys_prompt, prompt, tools=tools)

    if mode == MODE_MENTOR:
        reply, proposal = _advisor_reply(session, turn, snapshot)
        return AiCommandResult(
            reply=reply or "No pude armar una explicación para eso. ¿Podés reformular la pregunta?",
            actions=[], mode=MODE_MENTOR, proposal=proposal, revision=revision,
        )

    # Salvaguarda contra respuestas inventadas: si el pedido trae un verbo de
    # edicion y el modelo contesta SIN usar herramientas, suele "confirmar"
    # cambios que nunca hizo (observado con Gemini via la capa OpenAI-
    # compatible, y es comun en modelos locales chicos). Se le avisa una vez
    # y se le pide que las use. Si igual no lo hace, se reintenta UNA vez en
    # una sesion limpia (en la misma conversacion el modelo queda "anclado" a
    # su respuesta anterior: se observo que contestaba "tenes razon, ahi
    # ejecuto las herramientas" sin ejecutar nada). Si tampoco, NO se publica
    # su texto -- responde al aviso interno, que el usuario nunca vio, y
    # suele prometer cambios -- sino un mensaje honesto.
    if not turn.calls and _EDIT_RE.search(user_text):
        logger.info("[AI COMMAND] pedido de edicion sin tool calls: se insiste una vez")
        try:
            turn = session.insist_on_tools(INSIST_ON_TOOLS)
        except Exception as e:
            logger.warning(f"[AI COMMAND] fallo al insistir con herramientas: {e}")
            turn = llm_providers.Turn(text="")
        if not turn.calls:
            logger.info("[AI COMMAND] sigue sin tool calls: reintento en sesion limpia")
            try:
                session = llm_providers.open_session(cfg)
                turn = session.start(sys_prompt, prompt, tools=TOOLS)
            except Exception as e:
                logger.warning(f"[AI COMMAND] fallo el reintento: {e}")
                turn = llm_providers.Turn(text="")
        if not turn.calls:
            turn = llm_providers.Turn(text=NO_CHANGES_REPLY)

    for _ in range(MAX_TOOL_TURNS_SOLUTIONS if solutions_enabled else MAX_TOOL_TURNS):
        if not turn.calls:
            return AiCommandResult(reply=turn.text or "Listo.", actions=actions, mode=MODE_AUTO)

        results = []
        for call in turn.calls:
            logger.info(f"[AI TOOL] {call.name} -> {call.arguments}")
            try:
                fn = getattr(executor, call.name, None)
                if fn is None or call.name.startswith("_"):
                    raise ToolError(f"La herramienta '{call.name}' no existe.")
                result = fn(**call.arguments)
                actions.append({"tool": call.name, "input": call.arguments, "result": result})
                payload = json.dumps(result, ensure_ascii=False)
            except ToolError as e:
                payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            except Exception as e:
                logger.error(f"[AI TOOL] error ejecutando {call.name}: {e}")
                payload = json.dumps({"error": f"Error interno: {e}"}, ensure_ascii=False)
            results.append((call, payload))

        try:
            turn = session.send_tool_results(results)
        except Exception as e:
            # Las ediciones ya aplicadas siguen siendo validas (estan
            # commiteadas y emitidas por WebSocket): se informan como
            # resultado parcial en vez de propagar el error.
            logger.warning(f"[AI COMMAND] corte tras ejecutar {len(actions)} accion(es): {e}")
            hecho = _describe(actions)
            return AiCommandResult(
                reply=(
                    f"Apliqué {hecho}. Se cortó la conexión con el asistente antes de "
                    f"poder confirmarte el resto, así que revisá el diagrama por las dudas."
                    if hecho else
                    "No se pudo completar el comando: se cortó la conexión con el asistente."
                ),
                actions=actions,
            )

    hecho = _describe(actions)
    return AiCommandResult(
        reply=(
            f"Apliqué {hecho}, pero el comando era muy largo y quedó cortado. "
            f"Si falta algo, pedímelo en una instrucción más corta."
            if hecho else
            "El comando era demasiado complejo. Probá dividirlo en instrucciones más simples."
        ),
        actions=actions,
    )


# =====================================================================
# Ejecucion en segundo plano
# =====================================================================
# La capa gratuita de Gemini tiene latencia muy variable (medido: la misma
# llamada trivial tarda entre 2s y 90s), asi que dejar la peticion HTTP
# abierta esperando la respuesta es fragil y ademas congela la interfaz.
# En vez de eso el comando se procesa en segundo plano y el progreso viaja
# por el WebSocket que ya usa la colaboracion en tiempo real: el usuario ve
# aparecer cada clase/atributo en el diagrama a medida que se ejecutan.
# El runner en segundo plano vive en app/services/chat_service.py
# (run_ai_question_background), porque toda consulta a la IA pasa ahora por
# el chat grupal del diagrama.

# Mensajes segun el tipo de error. El SDK de Gemini expone la jerarquia de
# excepciones de la API de "interactions" desde un modulo interno, y depender
# de un import con "_" es fragil, asi que clasificamos por nombre de clase.
_ERROR_MESSAGES: dict[str, str] = {
    "authenticationerror": "La clave de API de Gemini no es válida. Revisá GEMINI_API_KEY en el archivo .env del backend.",
    "permissiondeniederror": "La clave de API de Gemini no tiene permiso para usar este modelo.",
    "ratelimiterror": "Se alcanzó el límite de uso gratuito de Gemini por hoy. Esperá unos minutos antes de reintentar.",
    "notfounderror": "El modelo de Gemini configurado no existe o ya no está disponible.",
    "badrequesterror": "Gemini rechazó la solicitud porque los parámetros eran inválidos.",
    "apitimeouterror": "Gemini tardó demasiado en responder. Volvé a intentarlo en un momento.",
    "apiconnectionerror": "No se pudo conectar con Gemini. Revisá tu conexión a internet.",
    "internalservererror": "Gemini tuvo un error interno. Reintentá en unos segundos.",
}


def describe_error(e: Exception) -> str:
    if isinstance(e, RuntimeError):  # incluye llm_providers.ProviderError
        return str(e)
    return _ERROR_MESSAGES.get(
        type(e).__name__.lower(),
        f"Error inesperado del asistente: {e}",
    )
