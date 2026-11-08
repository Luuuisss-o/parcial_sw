// lib/uap/response_phrasing.dart
//
// Convierte el resultado crudo de invocar una tool UAP (o el resultado de
// parsear la intención) en una frase natural en español -- nunca se le
// muestra JSON crudo al usuario como respuesta principal, ni en el modo
// Historial (donde se ve escrito) ni en el modo Alexa (donde encima hay
// que poder LEERLO en voz alta con TTS).

import 'intent_parser.dart';
import 'uap_manifest.dart';

/// Frase para el resultado de una invocación ya ejecutada contra el
/// backend (create/list/get/update/delete). "offline" indica que la
/// operación no se mandó todavía al servidor (se guardó en el outbox
/// local) -- en ese caso el texto nunca debe sonar a "ya se guardó en el
/// servidor", porque todavía no es verdad.
String phraseForResult({
  required String verb,
  required UapEntity entity,
  required Map<String, dynamic> result,
  bool offline = false,
}) {
  if (offline) {
    return switch (verb) {
      'create' => 'Guardé ${entity.label.toLowerCase()} en el teléfono. Lo voy a mandar apenas haya conexión.',
      'update' => 'Guardé el cambio en el teléfono. Se va a sincronizar apenas haya conexión.',
      'delete' => 'Marqué ${entity.label.toLowerCase()} para eliminar. Se va a sincronizar apenas haya conexión.',
      _ => 'La operación quedó pendiente de sincronización.',
    };
  }

  switch (verb) {
    case 'create':
      final name = _bestDisplayValue(result[entity.key]);
      return name != null
          ? 'Listo, registré ${entity.label.toLowerCase()} "$name".'
          : 'Listo, registré ${entity.label.toLowerCase()} nuevo/a.';
    case 'list':
      final items = (result[entity.plural] as List?) ?? const [];
      if (items.isEmpty) return 'No hay ${entity.plural} cargados todavía.';
      final shown = items.take(5).map((i) => _bestDisplayValue(i) ?? '').where((s) => s.isNotEmpty).join(', ');
      final rest = items.length > 5 ? ' y ${items.length - 5} más' : '';
      return 'Encontré ${items.length} ${items.length == 1 ? entity.label.toLowerCase() : entity.plural}: $shown$rest.';
    case 'get':
      final name = _bestDisplayValue(result[entity.key]);
      return name != null
          ? 'Encontré ${entity.label.toLowerCase()}: $name.'
          : 'Encontré ${entity.label.toLowerCase()}.';
    case 'update':
      return 'Actualicé ${entity.label.toLowerCase()} correctamente.';
    case 'delete':
      return 'Eliminé ${entity.label.toLowerCase()} correctamente.';
    default:
      return 'Listo.';
  }
}

/// Frase para un ParseResult que no llegó a ejecutarse (rechazado o
/// necesita más información) -- ya vienen con su propio mensaje en
/// español desde el parser, esto solo les da un tono consistente cuando
/// hace falta.
String phraseForParseResult(ParseResult result) {
  return switch (result) {
    ParsedInvocation() => 'Listo.', // no debería mostrarse, se reemplaza por phraseForResult tras ejecutar
    NeedsClarification(:final questionEs) => questionEs,
    Conversational(:final replyEs) => replyEs,
    Rejected(:final reasonEs) => 'No pude determinar una única acción: $reasonEs',
  };
}

String phraseForCancelled() => 'No se realizó la operación porque fue cancelada.';

String phraseForBackendRejected(String detail) => 'No pude realizar la operación porque el backend rechazó la solicitud: $detail';

String phraseForConflict() => 'Existe un conflicto con una versión más reciente del servidor.';

String phraseForGenerationReset() =>
    'La base de datos del servidor cambió desde la última vez. Actualicé los datos locales.';

/// Intenta extraer un valor "representativo" de un registro para mostrar
/// en la frase (el primer campo de tipo texto que no sea el id). No
/// conoce el dominio de antemano -- por eso es una heurística, no una
/// regla fija sobre un nombre de campo como "nombre".
String? _bestDisplayValue(dynamic record) {
  if (record is! Map) return null;
  for (final entry in record.entries) {
    if (entry.key == 'id') continue;
    final value = entry.value;
    if (value is String && value.trim().isNotEmpty) return value;
  }
  return null;
}
