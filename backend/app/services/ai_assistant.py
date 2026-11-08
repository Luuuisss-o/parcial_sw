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

from google import genai

from app.core.config import settings
from app.models.uml import Diagram
from app.services.ai_tools import DiagramToolExecutor, ToolError, TOOLS

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash-lite"
MAX_TOOL_TURNS = 6  # tope de vueltas del loop para evitar bucles infinitos
REQUEST_TIMEOUT = 45.0  # segundos por llamada; evita que cuelgue indefinidamente

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


def classify_intent(text: str) -> str:
    """MODE_MENTOR si la consulta es claramente teorica, MODE_AUTO si no.

    Teorica = empieza como pregunta/pedido de explicacion, o es una pregunta
    (lleva "?"), y en ningun caso contiene un verbo de edicion."""
    if _EDIT_RE.search(text):
        return MODE_AUTO
    if _THEORY_RE.search(text) or "?" in text:
        return MODE_MENTOR
    return MODE_AUTO

SYSTEM_PROMPT = """Sos el asistente de IA de un editor colaborativo de \
diagramas de clases UML, y cumplis DOS roles dentro del chat del equipo:

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
   pedir que te lo repitan paso a paso.
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
5. Restriccion de la catedra: no disenies el modelo completo por el \
   usuario. Si te describen un problema de negocio en general y te piden \
   que vos decidas las clases ("armame el diagrama de una veterinaria"), \
   no lo construyas: como mentor podes orientar (que preguntas hacerse, \
   que conceptos suelen aparecer), pero pedile que te indique que clases \
   quiere crear. Un pedido que YA nombra clases, atributos o relaciones \
   concretas NO entra en esta restriccion: eso ejecutalo siempre.
6. Al terminar, confirma en una o dos lineas exactamente que ejecutaste. \
   Nunca inventes cambios que no hiciste. Si una herramienta devuelve \
   error, leelo y corregi si podes; si no, explica que paso.
Un mensaje puede mezclar ambos roles ("que es una composicion? aplicala \
entre Pedido y Detalle"): ejecuta lo pedido y explica en pocas lineas (6 \
como maximo en total): la idea clave y por que la aplicaste asi.

FORMATO (el chat es angosto)
- Parrafos cortos. Podes usar listas con guiones, **negrita** para \
  resaltar un termino y `codigo` para nombres de clases/atributos/tipos.
- NO uses titulos (#, ##, ###), separadores (---), tablas ni emojis.

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
                 mode: str = "auto") -> str:
    """Arma el mensaje para el modelo con la memoria hibrida: quien pregunta,
    su hilo individual con la IA, la conversacion reciente del equipo y el
    estado actual del diagrama."""
    partes: list[str] = []
    if requester is not None:
        contacto = f" ({requester.email})" if requester.email else ""
        partes.append(f"Usuario que te consulta: {requester.name}{contacto}")

    partes.append(f"[Contexto global] Estado actual del diagrama (JSON):\n{state_json}")

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
            "Esta consulta es teorica/conceptual: responde como mentor, sin "
            "modificar el diagrama (en este turno no tenes herramientas)."
        )
    quien = f" de {requester.name}" if requester is not None else " del usuario"
    partes.append(f"Consulta actual{quien} (respondele a esta):\n{user_text}")
    return "\n\n".join(partes)


def run_command(db, diagram: Diagram, user_text: str, requester: Requester | None = None,
                history: list[tuple[str, str]] | None = None,
                team_context: list[TeamMessage] | None = None,
                mode: str | None = None) -> AiCommandResult:
    """Responde una consulta. `mode`:
      - MODE_MENTOR: pregunta teorica -> se llama al modelo SIN herramientas,
        asi es imposible que modifique el diagrama.
      - MODE_AUTO: el modelo decide (explicar, editar, o ambas).
    Si no se indica, se clasifica con classify_intent()."""
    mode = mode or classify_intent(user_text)
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY no esta configurada en el backend (.env)."
        )

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    executor = DiagramToolExecutor(db, diagram)

    state = json.dumps(executor.snapshot(), ensure_ascii=False)
    prompt = build_prompt(state, user_text, requester=requester, history=history,
                          team_context=team_context, mode=mode)

    actions: list[dict] = []

    def _ask(**kwargs):
        """Llama al modelo. Si se corta la comunicacion a mitad de un comando,
        las ediciones ya aplicadas siguen siendo validas (estan commiteadas y
        ya se emitieron por WebSocket), asi que no se pierden: se devuelven
        como resultado parcial en vez de propagar el error."""
        return client.interactions.create(timeout=REQUEST_TIMEOUT, **kwargs)

    try:
        first_call = dict(model=MODEL, input=prompt, system_instruction=SYSTEM_PROMPT)
        if mode != MODE_MENTOR:
            first_call["tools"] = TOOLS
        interaction = _ask(**first_call)
    except Exception:
        raise  # nada ejecutado todavia: que el router lo traduzca a un error claro

    if mode == MODE_MENTOR:
        return AiCommandResult(
            reply=interaction.output_text
            or "No pude armar una explicación para eso. ¿Podés reformular la pregunta?",
            actions=[], mode=MODE_MENTOR,
        )

    for _ in range(MAX_TOOL_TURNS):
        call_steps = [s for s in interaction.steps if s.type == "function_call"]
        if not call_steps:
            return AiCommandResult(reply=interaction.output_text or "Listo.", actions=actions, mode=MODE_AUTO)

        function_results = []
        for step in call_steps:
            logger.info(f"[AI TOOL] {step.name} -> {step.arguments}")
            try:
                fn = getattr(executor, step.name)
                result = fn(**step.arguments)
                actions.append({"tool": step.name, "input": step.arguments, "result": result})
                payload = json.dumps(result, ensure_ascii=False)
            except ToolError as e:
                payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            except Exception as e:
                logger.error(f"[AI TOOL] error ejecutando {step.name}: {e}")
                payload = json.dumps({"error": f"Error interno: {e}"}, ensure_ascii=False)

            function_results.append({
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": payload}],
            })

        try:
            # system_instruction se reenvia en cada vuelta: sin esto la
            # respuesta final (tras ejecutar herramientas) ignoraba las
            # reglas de formato y extension del prompt.
            interaction = _ask(
                model=MODEL,
                input=function_results,
                system_instruction=SYSTEM_PROMPT,
                tools=TOOLS,
                previous_interaction_id=interaction.id,
            )
        except Exception as e:
            # Se corto la comunicacion, pero lo ejecutado ya esta aplicado.
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
    if isinstance(e, RuntimeError):
        return str(e)
    return _ERROR_MESSAGES.get(
        type(e).__name__.lower(),
        f"Error inesperado del asistente: {e}",
    )
