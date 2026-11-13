// lib/services/local_llm_service.dart
//
// Asistente de IA corriendo ENTERAMENTE en el teléfono, sin red: un
// modelo de lenguaje chico (Gemma 3 1B IT, cuantizado GGUF Q4_K_M,
// empaquetado dentro del propio APK -- ver lib/services/model_downloader.dart)
// vía llamadart (bindings de llama.cpp).
//
// Esta clase se usa de DOS formas distintas:
// - resolveCommand(): el contrato original, específico del diagramador
//   (9 tools fijas: create_class, add_attribute, etc, ver ai_tools.py del
//   backend FastAPI). Se mantiene intacto, ese flujo sigue funcionando
//   igual que antes.
// - resolveUapCommand(): contrato genérico para CUALQUIER backend Spring
//   Boot generado (protocolo UAP, ver lib/uap/): el LLM nunca conoce las
//   tools de antemano, se le pasan las descubiertas en runtime contra ese
//   backend puntual. Un solo modelo, dos "modos" de prompt.
//
// En ambos casos, el LLM solo PROPONE {tool, args}: la autoridad real
// sobre qué tools existen y si los argumentos son válidos es siempre el
// parser determinista (ver lib/uap/intent_parser.dart para el caso UAP).
//
// Elegimos NO depender de tool-calling nativo del paquete (todavía cambia
// de versión en versión, y Gemma 3 no tiene un rol "system" real en su
// chat template): en cambio se le pide al modelo, por prompt, que
// responda un único objeto JSON con la función a llamar y sus
// argumentos, y se parsea acá con un extractor tolerante a texto extra
// alrededor (el modelo a veces agrega explicación antes/después del JSON
// a pesar de la instrucción). Es el mismo patrón defensivo que "function
// calling manual" en cualquier LLM sin soporte nativo confiable.

import 'dart:convert';
import 'package:llamadart/llamadart.dart';
import 'assistant_prompt.dart';

class LlmToolCall {
  final String tool;
  final Map<String, dynamic> arguments;
  LlmToolCall(this.tool, this.arguments);
}

/// Lo que el LLM puede devolver frente a un pedido en lenguaje natural:
/// o bien identificó una operación concreta (ToolProposal, que sigue
/// siendo solo una PROPUESTA -- IntentParser la valida antes de ejecutar
/// nada), o determinó que el usuario está charlando/preguntando algo
/// general y devuelve una respuesta de texto libre (ChatReply) para
/// mostrar tal cual, como cualquier asistente conversacional.
sealed class LlmResponse {}

class ToolProposal extends LlmResponse {
  final LlmToolCall call;
  ToolProposal(this.call);
}

class ChatReply extends LlmResponse {
  final String text;
  ChatReply(this.text);
}

class LocalLlmService {
  LlamaEngine? _engine;
  bool _loaded = false;
  String? _loadedPath;

  /// Nombre del modelo cargado, para mostrar en el chat qué modelo respondió
  /// (ej. "Gemma 3 1B personalizado v2026.11.08 (móvil)").
  String modelLabel = 'Gemma 3 1B (móvil)';

  bool get isLoaded => _loaded;

  static const _diagramSystemPrompt = '''
Sos un asistente que edita un diagrama de clases UML por instrucciones en
lenguaje natural. NUNCA generás el diagrama completo a partir de la
descripción de un problema: solo ejecutás la edición puntual que el usuario
te pide, una a la vez.

Herramientas disponibles (respondé SIEMPRE con un JSON de una de estas
formas, sin texto antes ni después):

{"tool": "create_class", "args": {"name": "Cliente"}}
{"tool": "add_attribute", "args": {"class_name": "Cliente", "name": "email", "type": "String", "required": false}}
{"tool": "add_method", "args": {"class_name": "Cliente", "name": "comprar", "return_type": "void"}}
{"tool": "create_relation", "args": {"from_class": "Cliente", "to_class": "Pedido", "type": "ASSOCIATION", "src_multiplicity": "1", "dst_multiplicity": "1..*"}}
{"tool": "rename_class", "args": {"class_name": "Cliente", "new_name": "Usuario"}}
{"tool": "delete_class", "args": {"class_name": "Cliente"}}
{"tool": "delete_attribute", "args": {"class_name": "Cliente", "attribute_name": "email"}}
{"tool": "delete_method", "args": {"class_name": "Cliente", "method_name": "comprar"}}
{"tool": "delete_relation", "args": {"from_class": "Cliente", "to_class": "Pedido"}}

Tipos de relación válidos: ASSOCIATION, AGGREGATION, COMPOSITION,
INHERITANCE, DEPENDENCY. Si no aclaran el tipo de atributo, usá "String"
para texto, "Integer" para números enteros, "Double" para montos, "Boolean"
para sí/no, "LocalDate" para fechas.

Si el pedido describe un problema general y te pide que VOS decidas qué
clases o relaciones debería tener el sistema (ej. "armame el diagrama de
una veterinaria"), respondé exactamente:
{"tool": "clarify", "args": {"message": "Decime qué clases, atributos o relaciones concretas querés que cree."}}
''';

  /// Copia (si hace falta) y carga el modelo. Llamar una sola vez al abrir
  /// el asistente por primera vez en la sesión.
  Future<void> load(String modelPath) async {
    if (_loaded && _loadedPath == modelPath) return;
    if (_loaded) await dispose(); // cambió el modelo (ej. llegó uno personalizado nuevo)
    _engine = LlamaEngine(LlamaBackend());
    await _engine!.loadModel(modelPath);
    _loaded = true;
    _loadedPath = modelPath;
  }

  Future<void> dispose() async {
    await _engine?.dispose();
    _engine = null;
    _loaded = false;
    _loadedPath = null;
  }

  /// Le pasa el estado actual del diagrama (clases/relaciones existentes,
  /// igual que hace el backend con Gemini) y la instrucción del usuario, y
  /// devuelve la llamada a función que el modelo decidió hacer. Contrato
  /// fijo del diagramador -- no se toca al agregar soporte UAP.
  Future<LlmToolCall> resolveCommand({
    required String userText,
    required Map<String, dynamic> diagramSnapshot,
  }) async {
    final prompt = '''
$_diagramSystemPrompt

Estado actual del diagrama (JSON): ${jsonEncode(diagramSnapshot)}

Instrucción del usuario: $userText
''';
    return parseToolCallFromRaw(await _generate(prompt));
  }

  /// Igual que resolveCommand, pero para un backend UAP genérico: las
  /// tools disponibles NO están hardcodeadas, se arman en runtime a partir
  /// de lo que ese backend puntual expuso en /uap/v1/tools.
  ///
  /// A diferencia de resolveCommand (que siempre fuerza un tool-call), acá
  /// el modelo puede elegir entre dos formas de responder: si identifica
  /// una operación concreta, propone {"tool":...,"args":...} (sigue siendo
  /// solo una PROPUESTA -- IntentParser la valida antes de ejecutar nada);
  /// si el pedido es charla general (una pregunta, un comentario, algo sin
  /// relación con las herramientas), responde {"chat": "..."} con texto
  /// libre que se muestra tal cual, como cualquier asistente conversacional.
  /// Ambos caminos en un solo prompt/llamada a propósito: una segunda
  /// llamada al LLM (primero "¿es operación o charla?", después resolver)
  /// duplicaría la latencia en un chip sin GPU como el Snapdragon 662.
  Future<LlmResponse> resolveUapCommand({
    required String userText,
    required List<UapToolSummary> tools,
  }) async {
    final toolsDescription = tools.map((t) => '- ${t.toolId}: ${t.description} (campos: ${t.fieldNames.join(', ')})').join('\n');

    final prompt = '''
Sos un asistente conversacional que además puede ejecutar operaciones
sobre un sistema, a partir de instrucciones en lenguaje natural en
español. Respondé SIEMPRE con un único JSON, sin texto antes ni después,
de una de estas dos formas:

1) Si el usuario pide crear, listar, consultar, actualizar o eliminar
   algo de las herramientas de abajo:
   {"tool": "<toolId de la lista>", "args": {"campo": "valor", ...}}
   No inventes campos que no estén en la lista de la herramienta elegida.

2) Si el usuario está charlando, preguntando algo general, o su pedido no
   corresponde a ninguna herramienta (saludo, pregunta sobre vos, charla
   casual, lo que sea):
   {"chat": "tu respuesta en español, natural y breve"}

Herramientas disponibles:
$toolsDescription

Instrucción del usuario: $userText
''';
    return parseLlmResponseFromRaw(await _generate(prompt, maxTokens: 300));
  }

  /// Responde una consulta del CHAT DEL EQUIPO con el modelo local, usando
  /// el mismo contrato con el que se entrenó el modelo personalizado
  /// (assistant_prompt.dart). `context` es lo que devuelve
  /// GET /diagrams/{id}/chat/{question_id}/context: quién pregunta, su hilo,
  /// la conversación del equipo y el diagrama (memoria híbrida).
  Future<AssistantReply> answerTeamQuestion(Map<String, dynamic> context) async {
    final prompt = formatGemmaChat(kTeamAssistantSystemPrompt, buildTeamAssistantUserMessage(context));
    final raw = await _generate(prompt, maxTokens: 512, temp: 0.2, stop: const ['<end_of_turn>']);
    return parseAssistantReply(raw);
  }

  Future<String> _generate(String prompt, {int maxTokens = 200, double temp = 0.1, List<String> stop = const []}) async {
    if (!_loaded || _engine == null) {
      throw StateError('El modelo local todavía no está cargado.');
    }
    final buffer = StringBuffer();
    // maxTokens/temp van dentro de GenerationParams en la API real de
    // llamadart (no como parametros sueltos de generate()). temp bajo
    // (0.1) a propósito incluso para las respuestas de charla: sigue
    // siendo un modelo de 1B parámetros con recursos muy limitados, y una
    // temperatura más alta aumenta el riesgo de que ni siquiera devuelva
    // JSON válido (ver extractFirstJsonObject/parseLlmResponseFromRaw,
    // que ya son tolerantes a texto extra alrededor por esta razón).
    await for (final token in _engine!.generate(
      prompt,
      params: GenerationParams(maxTokens: maxTokens, temp: temp, stopSequences: stop),
    )) {
      buffer.write(token);
    }
    return buffer.toString();
  }
}

/// Resumen mínimo de una tool UAP que el LLM necesita ver en el prompt --
/// no se le pasa el UapTool completo (con todo el detalle de tipos JSON-
/// Schema) para no inflar el prompt de un modelo tan chico como Gemma 1B.
class UapToolSummary {
  final String toolId;
  final String description;
  final List<String> fieldNames;
  UapToolSummary({required this.toolId, required this.description, required this.fieldNames});
}

/// Extrae un LlmToolCall del texto crudo que devolvió el modelo. Función
/// de nivel superior (no un método de instancia) para poder testearla sin
/// cargar ningún modelo real.
LlmToolCall parseToolCallFromRaw(String raw) {
  final jsonStr = extractFirstJsonObject(raw);
  if (jsonStr == null) {
    throw FormatException('El modelo no devolvió un JSON reconocible: $raw');
  }
  final data = jsonDecode(jsonStr) as Map<String, dynamic>;
  final tool = data['tool'] as String?;
  final args = (data['args'] as Map?)?.cast<String, dynamic>() ?? {};
  if (tool == null) {
    throw FormatException('La respuesta no tiene el campo "tool": $jsonStr');
  }
  return LlmToolCall(tool, args);
}

/// Igual que parseToolCallFromRaw, pero distingue el JSON de tool-call
/// ({"tool":...}) del de charla libre ({"chat":...}) -- ver
/// resolveUapCommand. Un objeto sin ninguno de los dos campos esperados
/// es un error de formato, igual que antes.
LlmResponse parseLlmResponseFromRaw(String raw) {
  final jsonStr = extractFirstJsonObject(raw);
  if (jsonStr == null) {
    throw FormatException('El modelo no devolvió un JSON reconocible: $raw');
  }
  final data = jsonDecode(jsonStr) as Map<String, dynamic>;

  final chat = data['chat'] as String?;
  if (chat != null) return ChatReply(chat);

  final tool = data['tool'] as String?;
  if (tool != null) {
    final args = (data['args'] as Map?)?.cast<String, dynamic>() ?? {};
    return ToolProposal(LlmToolCall(tool, args));
  }

  throw FormatException('La respuesta no tiene ni "tool" ni "chat": $jsonStr');
}

/// Busca el primer objeto JSON balanceado dentro de un texto -- el modelo
/// a veces envuelve el JSON en ```json ... ``` o agrega texto alrededor a
/// pesar de la instrucción, así que no se puede asumir que la respuesta
/// entera es JSON puro. Función pura y pública: es lo que permite
/// testear el extractor sin cargar ningún modelo.
String? extractFirstJsonObject(String raw) {
  final start = raw.indexOf('{');
  if (start == -1) return null;
  var depth = 0;
  for (var i = start; i < raw.length; i++) {
    if (raw[i] == '{') depth++;
    if (raw[i] == '}') {
      depth--;
      if (depth == 0) return raw.substring(start, i + 1);
    }
  }
  return null;
}
