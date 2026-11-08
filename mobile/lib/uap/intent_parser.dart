// lib/uap/intent_parser.dart
//
// El parser determinista es la AUTORIDAD sobre qué operación se ejecuta
// contra un backend UAP -- nunca el LLM local. El LLM (ver
// LocalLlmService.resolveUapCommand) solo PROPONE un borrador
// {tool, args} a partir del texto libre del usuario; este parser valida
// ese borrador contra el UapContract real (descubierto en runtime) y, si
// el LLM no dio un borrador utilizable, intenta resolver la intención por
// su cuenta con reglas fijas sobre el texto crudo. En ningún caso se
// ejecuta un toolId o un campo que no exista en el contrato descubierto.
//
// Todo el pipeline es sincrónico, sin red y sin el LLM adentro: es lo que
// permite testear cada regla (alias en español, plurales, sanitización,
// coerción) de forma aislada y determinista.

import 'type_coercion.dart';
import 'uap_manifest.dart';

sealed class ParseResult {}

class ParsedInvocation extends ParseResult {
  final String toolId;
  final Map<String, dynamic> input;
  ParsedInvocation(this.toolId, this.input);
}

class NeedsClarification extends ParseResult {
  final String questionEs;
  /// Lo que ya se resolvió en ESTE turno, para que el próximo mensaje del
  /// usuario (que probablemente responda solo la parte que falta, ej.
  /// "crear" después de "¿qué querés hacer con bank?") no tenga que repetir
  /// todo desde cero. Ver ConversationContext.
  final ConversationContext context;
  NeedsClarification(this.questionEs, {ConversationContext? context}) : context = context ?? const ConversationContext();
}

class Rejected extends ParseResult {
  final String reasonEs;
  Rejected(this.reasonEs);
}

/// El texto no es un pedido de operación (saludo, agradecimiento,
/// pregunta sobre qué puede hacer el asistente, charla casual). Distinto
/// de Rejected a propósito: Rejected significa "entendí que querías hacer
/// algo, pero no puedo"; Conversational significa "esto no es un pedido,
/// así que respondo como charla" -- la UI los muestra distinto (uno como
/// error/aviso, el otro como una respuesta normal del asistente).
class Conversational extends ParseResult {
  final String replyEs;
  Conversational(this.replyEs);
}

/// Lo que el LLM local propone antes de que el parser lo valide -- mismo
/// shape que ya produce LocalLlmService.resolveCommand para el diagramador
/// (ver LlmToolCall), reusado acá para el flujo UAP.
class LlmDraft {
  final String? entityHint; // lo que el LLM entendio como la entidad (puede venir mal)
  final String? verbHint; // lo que el LLM entendio como el verbo (puede venir mal)
  final Map<String, dynamic> fields;
  LlmDraft({this.entityHint, this.verbHint, this.fields = const {}});
}

/// Memoria de UN turno de conversación (no una sesión entera): qué
/// entidad/verbo/campos ya quedaron resueltos antes de pedir una
/// aclaración. Sin esto, "crear" como respuesta a "¿qué querés hacer con
/// bank?" se evaluaba aislado -- sin ninguna entidad en el propio texto,
/// entonces fallaba con "no reconozco esa entidad" en vez de recordar que
/// ya se había hablado de "bank" un mensaje antes.
///
/// Deliberadamente chico y de un solo nivel (no una pila de todo el
/// historial): el objetivo es completar el huequito que falta en la
/// respuesta inmediata siguiente, no razonar sobre una conversación larga
/// -- eso ya lo intenta el LLM con el texto completo que se le pasa.
class ConversationContext {
  final String? entityKey;
  final String? verb;
  final Map<String, dynamic> fields;

  const ConversationContext({this.entityKey, this.verb, this.fields = const {}});

  bool get isEmpty => entityKey == null && verb == null && fields.isEmpty;
}

const Map<String, String> _verbAliases = {
  // create
  'crear': 'create', 'crea': 'create', 'creá': 'create',
  'registrar': 'create', 'registra': 'create', 'registrá': 'create',
  'agregar': 'create', 'agrega': 'create', 'agregá': 'create',
  'añadir': 'create', 'añade': 'create', 'añadí': 'create',
  'nuevo': 'create', 'nueva': 'create', 'anotar': 'create', 'anotá': 'create',
  // list
  'listar': 'list', 'lista': 'list', 'listame': 'list', 'listá': 'list',
  'mostrar': 'list', 'muestra': 'list', 'mostrame': 'list',
  'ver': 'list', 'dame': 'list', 'cuales': 'list', 'cuáles': 'list',
  // get
  'consultar': 'get', 'consulta': 'get', 'consultá': 'get',
  'obtener': 'get', 'obtené': 'get', 'buscar': 'get', 'buscá': 'get',
  'traer': 'get', 'traé': 'get',
  // update
  'actualizar': 'update', 'actualizá': 'update', 'actualiza': 'update',
  'modificar': 'update', 'modificá': 'update', 'modifica': 'update',
  'cambiar': 'update', 'cambiá': 'update', 'cambia': 'update',
  'editar': 'update', 'editá': 'update', 'corregir': 'update', 'corregí': 'update',
  // delete
  'eliminar': 'delete', 'eliminá': 'delete', 'elimina': 'delete',
  'borrar': 'delete', 'borrá': 'delete', 'borra': 'delete',
  'quitar': 'delete', 'quitá': 'delete',
};

// Patrones que nunca deben aparecer en un valor de campo -- ni siquiera
// como texto libre. No son una lista de "malas palabras" sino un intento
// de reconocer que el valor dejó de ser un dato y pasó a ser una
// instrucción/payload (URL arbitraria, SQL, shell, reflexión de Java).
final List<RegExp> _forbiddenValuePatterns = [
  RegExp(r'https?://', caseSensitive: false),
  RegExp(r';\s*--'),
  RegExp(r'\b(drop|select|insert|delete\s+from|union)\b', caseSensitive: false),
  RegExp(r'`|\$\(|&&|\|\|'),
  RegExp(r'class\.forname|getdeclaredmethod|\.invoke\(', caseSensitive: false),
];

String _stripAccents(String s) {
  const from = 'áéíóúÁÉÍÓÚñÑ';
  const to = 'aeiouAEIOUnN';
  var out = s;
  for (var i = 0; i < from.length; i++) {
    out = out.replaceAll(from[i], to[i]);
  }
  return out;
}

/// Singular<->plural español simplificado: suficiente para lo que un
/// manifest UAP declara (nombres de entidad simples, sin plurales
/// irregulares como "lápiz"->"lápices" en la mayoría de los dominios de
/// examen). No pretende ser un lematizador completo del idioma.
List<String> _candidateSingularsAndPlurals(String word) {
  final w = word.toLowerCase();
  final candidates = <String>{w};
  if (w.endsWith('es') && w.length > 3) candidates.add(w.substring(0, w.length - 2));
  if (w.endsWith('s') && w.length > 2) candidates.add(w.substring(0, w.length - 1));
  candidates.add('${w}s');
  candidates.add('${w}es');
  return candidates.toList();
}

int _levenshtein(String a, String b) {
  final dp = List.generate(a.length + 1, (_) => List.filled(b.length + 1, 0));
  for (var i = 0; i <= a.length; i++) {
    dp[i][0] = i;
  }
  for (var j = 0; j <= b.length; j++) {
    dp[0][j] = j;
  }
  for (var i = 1; i <= a.length; i++) {
    for (var j = 1; j <= b.length; j++) {
      final cost = a[i - 1] == b[j - 1] ? 0 : 1;
      dp[i][j] = [dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost].reduce((x, y) => x < y ? x : y);
    }
  }
  return dp[a.length][b.length];
}

/// Patrones que identifican charla casual (no un pedido de operación).
/// Deliberadamente chicos y específicos -- el objetivo NO es un detector
/// de intención general, es distinguir "esto no es una orden" de "no
/// entendí la orden", para que el asistente no suene a error cada vez que
/// alguien saluda.
final _greetingRe = RegExp(r'^(hola|holis|buenas|buenos dias|buenas tardes|buenas noches|hey|ey)\b');
final _thanksRe = RegExp(r'\b(gracias|muchas gracias|genial|perfecto|buenisimo|excelente)\b');
final _helpRe = RegExp(r'\b(que podes hacer|que puedes hacer|ayuda|que haces|en que me ayudas|como funciona)\b');
final _farewellRe = RegExp(r'^(chau|adios|nos vemos|hasta luego|bye)\b');

class IntentParser {
  final UapContract contract;
  IntentParser(this.contract);

  ParseResult parse(String userText, {LlmDraft? draft, ConversationContext previous = const ConversationContext()}) {
    final normalized = _stripAccents(userText.toLowerCase()).trim();
    if (normalized.isEmpty) return Rejected('No entendí ningún pedido.');

    // La charla casual siempre gana primero -- pero solo si NO había una
    // aclaración pendiente. Si el usuario ya venía respondiendo "¿qué
    // querés hacer con X?" y dice "gracias" en vez de un verbo, es mejor
    // tratarlo como "no entendí, segui" en vez de cortar la conversación
    // con un genérico "de nada".
    if (previous.isEmpty) {
      final casual = _detectCasualChat(normalized);
      if (casual != null) return Conversational(casual);
    }

    // Resolver entidad: primero el texto actual (y el hint del LLM), y
    // solo si ninguno de los dos trae nada, caer al contexto del turno
    // anterior -- así "creá OTRO banco" en medio de la conversación sigue
    // pudiendo cambiar de entidad, en vez de quedar pegado a la primera.
    final resolvedEntity = _resolveEntity(normalized, draft?.entityHint) ??
        (previous.entityKey != null ? contract.entitiesByAlias[previous.entityKey] : null);
    if (resolvedEntity == null) {
      return Rejected(
        'No reconozco esa entidad en este sistema. Las que existen son: '
        '${contract.manifest.entities.map((e) => e.label).join(', ')}.',
      );
    }
    final entity = resolvedEntity; // no-nullable a partir de acá, para closures como el de abajo

    var verb = _resolveVerb(normalized, draft?.verbHint);
    verb ??= previous.verb;
    if (verb == null) {
      return NeedsClarification(
        '¿Qué querés hacer con ${entity.plural}: crear, listar, consultar, actualizar o eliminar?',
        context: ConversationContext(entityKey: entity.key),
      );
    }

    final tool = contract.toolFor(verb, entity.key);
    if (tool == null) {
      return Rejected(
        'Ese backend no permite "$verb" sobre ${entity.label}. '
        'Las operaciones disponibles son: ${contract.tools.where((t) => t.entityKey == entity.key).map((t) => t.verb).join(', ')}.',
      );
    }

    // Los campos SÍ se acumulan con lo ya dicho en turnos anteriores (a
    // diferencia de entidad/verbo, que se reemplazan): si el usuario ya
    // dio el nombre y ahora completa el precio que faltaba, el nombre no
    // debe perderse.
    final draftFields = {...previous.fields, ...(draft?.fields ?? const {})};
    for (final key in draftFields.keys) {
      if (!tool.properties.containsKey(key)) {
        return Rejected(
          'El campo "$key" no existe para ${entity.label}. '
          'Los campos válidos son: ${tool.properties.keys.join(', ')}.',
        );
      }
    }

    final coercedInput = <String, dynamic>{};
    for (final entry in draftFields.entries) {
      final raw = entry.value;
      if (raw is String) {
        for (final pattern in _forbiddenValuePatterns) {
          if (pattern.hasMatch(raw)) {
            return Rejected('El valor de "${entry.key}" contiene algo que no puedo aceptar como dato.');
          }
        }
      }
      final schema = tool.properties[entry.key]!;
      final result = coerce(declaredType: schema.type, format: schema.format, raw: raw);
      switch (result) {
        case Coerced(:final value):
          coercedInput[entry.key] = value;
        case CoercionFailed(:final messageEs):
          return NeedsClarification(
            messageEs,
            context: ConversationContext(entityKey: entity.key, verb: verb, fields: draftFields),
          );
      }
    }

    final missing = tool.required.where((f) => !coercedInput.containsKey(f)).toList();
    if (missing.isNotEmpty) {
      return NeedsClarification(
        'Me falta el campo "${missing.first}" para ${_verbDescriptionEs(verb)} ${entity.label}.',
        context: ConversationContext(entityKey: entity.key, verb: verb, fields: coercedInput),
      );
    }

    return ParsedInvocation(tool.toolId, coercedInput);
  }

  /// null si el texto no matchea ningún patrón de charla casual -- en ese
  /// caso el pipeline sigue de largo tratándolo como un posible pedido de
  /// operación, como siempre.
  String? _detectCasualChat(String normalizedText) {
    if (_greetingRe.hasMatch(normalizedText)) {
      final entities = contract.manifest.entities.map((e) => e.label).join(', ');
      return entities.isEmpty
          ? '¡Hola! Todavía no descubrí ninguna entidad en este backend.'
          : '¡Hola! Puedo ayudarte con: $entities. ¿Qué necesitás hacer?';
    }
    if (_helpRe.hasMatch(normalizedText)) {
      final entities = contract.manifest.entities.map((e) => e.label).join(', ');
      final example = contract.manifest.entities.isNotEmpty ? contract.manifest.entities.first : null;
      return example == null
          ? 'Puedo crear, listar, consultar, actualizar o eliminar registros, pero todavía no descubrí ninguna entidad en este backend.'
          : 'Puedo crear, listar, consultar, actualizar o eliminar registros de: $entities. '
              'Por ejemplo: "creá un/a ${example.label} nuevo/a" o "listame los ${example.plural}".';
    }
    if (_farewellRe.hasMatch(normalizedText)) {
      return '¡Nos vemos!';
    }
    if (_thanksRe.hasMatch(normalizedText)) {
      return '¡De nada! Avisame si necesitás algo más.';
    }
    return null;
  }

  UapEntity? _resolveEntity(String normalizedText, String? hint) {
    if (hint != null) {
      final byHint = contract.entitiesByAlias[_stripAccents(hint.toLowerCase())];
      if (byHint != null) return byHint;
    }
    // Buscar cualquier alias conocido (o su singular/plural) como palabra
    // dentro del texto normalizado.
    for (final alias in contract.entitiesByAlias.keys) {
      for (final candidate in _candidateSingularsAndPlurals(alias)) {
        if (normalizedText.contains(candidate)) return contract.entitiesByAlias[alias];
      }
    }
    // Tolerancia a typos: distancia de edicion <= 1 contra cada palabra
    // del texto para cada alias conocido.
    final words = normalizedText.split(RegExp(r'\s+'));
    for (final word in words) {
      for (final alias in contract.entitiesByAlias.keys) {
        if (_levenshtein(word, alias) <= 1) return contract.entitiesByAlias[alias];
      }
    }
    return null;
  }

  String? _resolveVerb(String normalizedText, String? hint) {
    if (hint != null) {
      final h = _stripAccents(hint.toLowerCase());
      if (_verbAliases.containsValue(h)) return h; // el LLM ya devolvio el verbo canonico
      if (_verbAliases.containsKey(h)) return _verbAliases[h];
    }
    for (final word in normalizedText.split(RegExp(r'\s+'))) {
      if (_verbAliases.containsKey(word)) return _verbAliases[word];
    }
    return null;
  }

  String _verbDescriptionEs(String verb) => switch (verb) {
        'create' => 'crear',
        'list' => 'listar',
        'get' => 'consultar',
        'update' => 'actualizar',
        'delete' => 'eliminar',
        _ => verb,
      };
}
