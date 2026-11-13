// lib/services/assistant_prompt.dart
//
// Contrato del modelo PERSONALIZADO que corre en el celular para el chat del
// equipo (Fase 2). Es la ÚNICA fuente de verdad del formato:
//
//   - training/build_dataset.py lee kTeamAssistantSystemPrompt de ESTE
//     archivo (entre los marcadores BEGIN/END) para generar los ejemplos de
//     entrenamiento con exactamente el mismo prompt que se usa en la app.
//   - buildTeamAssistantUserMessage() tiene su gemela en Python
//     (training/prompt_contract.py). Las dos se verifican contra el mismo
//     caso de referencia (training/fixtures/context_example*.{json,txt}),
//     en test/services/assistant_prompt_test.dart y en
//     training/tests/test_prompt_contract.py: si alguien cambia una sin la
//     otra, falla un test.
//
// Si el prompt del modelo en el celular no coincide con el del
// entrenamiento, el modelo personalizado pierde casi todo lo que aprendió.
//
// Formato de salida (un único JSON, sin texto alrededor):
//   {"say": "Ana, ...", "actions": [{"tool": "create_class", "args": {...}}, ...]}
// - Pregunta teórica (mentoría): "actions" vacío.
// - Edición: una o varias acciones + "say" confirmando lo hecho.

import 'dart:convert';

// BEGIN_SYSTEM_PROMPT
const String kTeamAssistantSystemPrompt = '''Sos un integrante más del equipo que diseña un diagrama de clases UML: desarrollador senior, moderador y mentor de diseño de software. Varios compañeros te escriben en el chat grupal y todos ven tus respuestas.

Reglas:
1. Respondé SOLO a la consulta actual, dirigiéndote a quien pregunta por su nombre de pila al empezar ("Ana, ...").
2. Pregunta teórica (UML, patrones, requerimientos, principios de diseño): explicá en 2 a 6 líneas con un ejemplo, sin acciones. Si sirve, usá el diagrama actual como ejemplo.
3. Pedido de edición: generá las acciones necesarias y confirmá en una línea lo que hiciste. Nunca afirmes un cambio que no está en "actions".
4. Si no aclaran el tipo de un atributo: String para textos, Integer para cantidades, Double para montos, LocalDate para fechas, Boolean para sí/no. Si no aclaran el tipo de relación: ASSOCIATION.
5. Entrega de soluciones: si está DESACTIVADA y te piden diseñar el sistema completo ("armame el diagrama de una veterinaria"), no lo construyas: orientá y pedí qué clases crear. Si está ACTIVADA, diseñá una solución acotada (3 a 6 clases) con sus atributos y relaciones.
6. Usá el hilo de la persona para entender referencias ("agregale otro atributo", "esa clase") y la conversación del equipo como contexto.
7. Revisión del diagrama actual ("¿cómo relacionamos X e Y?", "revisá la cardinalidad", "¿qué le falta a X?"): explicá el diagnóstico y la recomendación en 2 a 6 líneas y poné en "actions" los cambios concretos que proponés; quedan como PROPUESTA que el equipo revisa antes de aplicar, así que decí que los dejás propuestos. Si ya está bien, decilo y no propongas nada. Las relaciones se muestran como Origen -[TIPO multOrigen → multDestino]-> Destino; para cambiar la multiplicidad de una existente: delete_relation y create_relation.

Herramientas (campo "tool" y sus "args"):
- create_class {"name"}
- rename_class {"class_name", "new_name"}
- delete_class {"class_name"}
- add_attribute {"class_name", "name", "type", "required"}
- delete_attribute {"class_name", "attribute_name"}
- add_method {"class_name", "name", "return_type"}
- delete_method {"class_name", "method_name"}
- create_relation {"from_class", "to_class", "type", "src_multiplicity", "dst_multiplicity"} con type en ASSOCIATION, AGGREGATION, COMPOSITION, INHERITANCE, DEPENDENCY (herencia: de la hija al padre; agregación y composición: de la parte al todo)
- delete_relation {"from_class", "to_class"}

Respondé SIEMPRE con un único JSON y nada más:
{"say": "texto para quien pregunta", "actions": [{"tool": "...", "args": {...}}]}''';
// END_SYSTEM_PROMPT

/// Diagrama en texto compacto (un modelo de 1B tiene poco contexto útil):
///   Cliente(nombre: String, email: String; comprar(): void)
///   Cliente -[ASSOCIATION 1..*]-> Pedido
String compactDiagram(Map<String, dynamic> diagram) {
  final lines = <String>[];
  for (final c in (diagram['clases'] as List? ?? const [])) {
    final attrs = [
      for (final a in (c['atributos'] as List? ?? const [])) '${a['nombre']}: ${a['tipo']}',
    ];
    final methods = [
      for (final m in (c['metodos'] as List? ?? const [])) '${m['nombre']}(): ${m['tipo_retorno']}',
    ];
    final body = [if (attrs.isNotEmpty) attrs.join(', '), if (methods.isNotEmpty) methods.join(', ')].join('; ');
    lines.add('${c['nombre']}($body)');
  }
  for (final r in (diagram['relaciones'] as List? ?? const [])) {
    // Con multiplicidades (si vienen): Cliente -[ASSOCIATION 1 → 0..*]-> Pedido.
    final mult = r['mult_origen'] != null && r['mult_destino'] != null
        ? ' ${r['mult_origen']} → ${r['mult_destino']}'
        : '';
    lines.add('${r['origen']} -[${r['tipo']}$mult]-> ${r['destino']}');
  }
  return lines.isEmpty ? '(vacío)' : lines.join('\n');
}

/// Mensaje de usuario con la memoria híbrida, a partir del contexto que
/// devuelve GET /diagrams/{id}/chat/{question_id}/context.
String buildTeamAssistantUserMessage(Map<String, dynamic> ctx) {
  final name = ctx['requester_name'] as String;
  final b = StringBuffer()
    ..writeln('Quien pregunta: $name')
    ..writeln('Entrega de soluciones: ${(ctx['solutions_enabled'] as bool? ?? false) ? 'ACTIVADA' : 'DESACTIVADA'}')
    ..writeln()
    ..writeln('Diagrama actual:')
    ..writeln(compactDiagram((ctx['diagram'] as Map?)?.cast<String, dynamic>() ?? const {}));

  final team = (ctx['team_context'] as List? ?? const []);
  if (team.isNotEmpty) {
    b
      ..writeln()
      ..writeln('Conversación reciente del equipo:');
    for (final m in team) {
      if (m['is_ai'] == true) {
        b.writeln('- IA (a ${m['addressed_to'] ?? 'alguien'}): ${m['content']}');
      } else {
        b.writeln('- ${m['author']}: ${m['content']}');
      }
    }
  }

  final history = (ctx['history'] as List? ?? const []);
  if (history.isNotEmpty) {
    b
      ..writeln()
      ..writeln('Consultas previas de $name a la IA:');
    for (final h in history) {
      b
        ..writeln('- $name: ${h['question']}')
        ..writeln('  IA: ${h['answer']}');
    }
  }

  b
    ..writeln()
    ..write('Consulta actual de $name: ${ctx['question']}');
  return b.toString();
}

/// Plantilla de chat de Gemma 3 (no tiene rol "system": el prompt de sistema
/// va al principio del primer turno de usuario, igual que hace el chat
/// template oficial y, por lo tanto, igual que en el entrenamiento).
String formatGemmaChat(String system, String user) =>
    '<start_of_turn>user\n$system\n\n$user<end_of_turn>\n<start_of_turn>model\n';

/// Una acción que el modelo propone ejecutar sobre el diagrama.
class AssistantAction {
  final String tool;
  final Map<String, dynamic> args;
  const AssistantAction(this.tool, this.args);
  Map<String, dynamic> toJson() => {'tool': tool, 'args': args};
}

/// Respuesta del modelo ya parseada.
class AssistantReply {
  final String say;
  final List<AssistantAction> actions;
  const AssistantReply(this.say, this.actions);
}

/// Parser tolerante: el modelo chico a veces envuelve el JSON en ```json,
/// agrega texto alrededor, o usa los formatos viejos de la app
/// ({"tool":..} suelto, {"chat": ...}). Si no hay ningún JSON válido, el
/// texto entero se toma como respuesta sin acciones.
AssistantReply parseAssistantReply(String raw) {
  final jsonStr = _firstJsonObject(raw);
  if (jsonStr != null) {
    try {
      final data = jsonDecode(jsonStr);
      if (data is Map<String, dynamic>) {
        final say = (data['say'] ?? data['chat'] ?? data['message'] ?? '').toString().trim();
        final actions = <AssistantAction>[];
        final rawActions = data['actions'];
        if (rawActions is List) {
          for (final a in rawActions) {
            if (a is Map && a['tool'] is String) {
              actions.add(AssistantAction(a['tool'] as String, (a['args'] as Map?)?.cast<String, dynamic>() ?? {}));
            }
          }
        } else if (data['tool'] is String) {
          actions.add(AssistantAction(data['tool'] as String, (data['args'] as Map?)?.cast<String, dynamic>() ?? {}));
        }
        return AssistantReply(say, actions);
      }
    } on FormatException {
      // cae al texto plano
    }
  }
  return AssistantReply(raw.trim(), const []);
}

String? _firstJsonObject(String raw) {
  final start = raw.indexOf('{');
  if (start == -1) return null;
  var depth = 0;
  var inString = false;
  var escaped = false;
  for (var i = start; i < raw.length; i++) {
    final ch = raw[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch == r'\') {
        escaped = true;
      } else if (ch == '"') {
        inString = false;
      }
      continue;
    }
    if (ch == '"') inString = true;
    if (ch == '{') depth++;
    if (ch == '}') {
      depth--;
      if (depth == 0) return raw.substring(start, i + 1);
    }
  }
  return null;
}
