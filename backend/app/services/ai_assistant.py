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
from dataclasses import dataclass, field

from google import genai

from app.core.config import settings
from app.models.uml import Diagram
from app.services.ai_tools import DiagramToolExecutor, ToolError, TOOLS

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash-lite"
MAX_TOOL_TURNS = 6  # tope de vueltas del loop para evitar bucles infinitos
REQUEST_TIMEOUT = 45.0  # segundos por llamada; evita que cuelgue indefinidamente

SYSTEM_PROMPT = """Sos el asistente de edicion de un editor colaborativo de \
diagramas de clases UML. Un disenador de software te da instrucciones en \
lenguaje natural (por texto o por voz ya transcripta) y vos las ejecutas \
llamando a las herramientas disponibles para editar el diagrama.

Como trabajas:
1. Ejecuta SIEMPRE lo que el usuario pide, usando las herramientas. Sos un \
   ejecutor: si el pedido nombra los elementos concretos, hacelo sin pedir \
   confirmacion ni pedir que te lo repitan paso a paso.
2. Un solo mensaje del usuario puede implicar VARIAS herramientas, y esta \
   perfecto encadenarlas. Ejemplos que SI debes ejecutar completos:
   - "crea la clase Usuario y agregale nombre, ci, contrasena y correo" \
     -> create_class(Usuario) + 4 add_attribute.
   - "crea Cliente y Pedido y relacionalos de uno a muchos" \
     -> 2 create_class + create_relation.
   - "a Factura ponele total decimal y fecha date" -> 2 add_attribute.
3. Si el usuario no aclara el tipo de un atributo, elegi vos el tipo mas \
   razonable (String para nombres/correos/textos, Integer para cantidades, \
   Double para montos, LocalDate para fechas, Boolean para si/no) y segui \
   adelante. No frenes para preguntar por algo tan menor.
4. Si el usuario no aclara el tipo de una relacion, usa ASSOCIATION.

Unica restriccion (requisito de la catedra): no disenies el modelo por el \
usuario. Es decir, si te describen un problema de negocio en general y te \
piden que vos decidas que clases y relaciones deberia tener (ej: "armame el \
diagrama para un sistema de una veterinaria", "diseñame la base de datos de \
un colegio"), ahi si respondé que vos ejecutas ediciones y que te indique \
que clases quiere. Ojo: un pedido que YA nombra las clases, atributos o \
relaciones concretas NO entra en esta restriccion: eso ejecutalo siempre.

Respuesta final: en español, en una o dos lineas, confirmando exactamente \
que ejecutaste. Nunca inventes cambios que no hiciste. Si una herramienta \
devuelve error, leelo y corregi si podes (ej. el usuario escribio mal un \
nombre que se parece a una clase existente); si no podes, explicale al \
usuario que paso.

Chat grupal (varios usuarios a la vez):
- Trabajas dentro del chat grupal del diagrama. Varios colaboradores te \
  escriben y TODOS ven tus respuestas, asi que en cada consulta se te indica \
  QUIEN te esta preguntando (nombre y email).
- Dirigite SIEMPRE a esa persona por su nombre de pila al empezar la \
  respuesta (ej: "Ana, ya cree la clase Cliente..."). Nunca le respondas a \
  otro colaborador ni mezcles su pedido con el de otra persona.
- Si se te pasan consultas previas de esa misma persona, usalas para \
  entender referencias como "agregale otro atributo" o "esa clase", pero \
  responde solo a la consulta actual.
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


def build_prompt(state_json: str, user_text: str, requester: Requester | None = None,
                 history: list[tuple[str, str]] | None = None) -> str:
    """Arma el mensaje para el modelo: quien pregunta, su historial con la IA
    en este diagrama y el estado actual del diagrama."""
    partes: list[str] = []
    if requester is not None:
        contacto = f" ({requester.email})" if requester.email else ""
        partes.append(f"Usuario que te consulta: {requester.name}{contacto}")
        if history:
            lineas = [f"Consultas previas de {requester.name} en este diagrama (de la mas vieja a la mas nueva):"]
            for i, (pregunta, respuesta) in enumerate(history, 1):
                lineas.append(f"{i}. {requester.name} pregunto: {pregunta}")
                lineas.append(f"   Vos respondiste: {respuesta}")
            partes.append("\n".join(lineas))
    partes.append(f"Estado actual del diagrama (JSON):\n{state_json}")
    quien = f" de {requester.name}" if requester is not None else " del usuario"
    partes.append(f"Instruccion actual{quien}:\n{user_text}")
    return "\n\n".join(partes)


def run_command(db, diagram: Diagram, user_text: str, requester: Requester | None = None,
                history: list[tuple[str, str]] | None = None) -> AiCommandResult:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY no esta configurada en el backend (.env)."
        )

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    executor = DiagramToolExecutor(db, diagram)

    state = json.dumps(executor.snapshot(), ensure_ascii=False)
    prompt = build_prompt(state, user_text, requester=requester, history=history)

    actions: list[dict] = []

    def _ask(**kwargs):
        """Llama al modelo. Si se corta la comunicacion a mitad de un comando,
        las ediciones ya aplicadas siguen siendo validas (estan commiteadas y
        ya se emitieron por WebSocket), asi que no se pierden: se devuelven
        como resultado parcial en vez de propagar el error."""
        return client.interactions.create(timeout=REQUEST_TIMEOUT, **kwargs)

    try:
        interaction = _ask(
            model=MODEL,
            input=prompt,
            system_instruction=SYSTEM_PROMPT,
            tools=TOOLS,
        )
    except Exception:
        raise  # nada ejecutado todavia: que el router lo traduzca a un error claro

    for _ in range(MAX_TOOL_TURNS):
        call_steps = [s for s in interaction.steps if s.type == "function_call"]
        if not call_steps:
            return AiCommandResult(reply=interaction.output_text or "Listo.", actions=actions)

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
            interaction = _ask(
                model=MODEL,
                input=function_results,
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
