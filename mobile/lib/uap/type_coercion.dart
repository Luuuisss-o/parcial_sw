// lib/uap/type_coercion.dart
//
// Convierte un valor "crudo" (típicamente lo que salió del LLM local o de
// lo que el usuario tipeó/dijo) al tipo que el schema UAP de un campo
// declara. Función pura y sin dependencias de red/IO a propósito: es el
// bloque más fácil de romper por accidente (fechas, separadores de miles,
// booleanos en español) y necesita ser 100% testeable sin mockear nada.
//
// Nunca lanza excepciones -- un valor imposible de convertir devuelve
// CoercionFailed con un mensaje en español listo para mostrarle al
// usuario o para que el modo Alexa lo lea en voz alta, en vez de que el
// error se propague como una excepción cruda de Dart en medio del flujo
// de UI.

sealed class CoercionResult {}

class Coerced extends CoercionResult {
  final Object? value;
  Coerced(this.value);
}

class CoercionFailed extends CoercionResult {
  final String messageEs;
  CoercionFailed(this.messageEs);
}

const _trueWords = {'true', '1', 'si', 'sí', 'verdadero', 'activo'};
const _falseWords = {'false', '0', 'no', 'falso', 'inactivo'};

CoercionResult coerce({required String declaredType, String? format, required Object? raw}) {
  if (raw == null) return Coerced(null);

  switch (declaredType) {
    case 'boolean':
      return _coerceBoolean(raw);
    case 'integer':
      return _coerceInteger(raw);
    case 'number':
      return _coerceNumber(raw, format);
    case 'string':
      return _coerceString(raw, format);
    default:
      // Tipo declarado desconocido: no inventar una conversion, dejar el
      // valor tal cual como string -- mas seguro que asumir un tipo.
      return Coerced(raw.toString());
  }
}

CoercionResult _coerceBoolean(Object raw) {
  if (raw is bool) return Coerced(raw);
  final s = raw.toString().trim().toLowerCase();
  if (_trueWords.contains(s)) return Coerced(true);
  if (_falseWords.contains(s)) return Coerced(false);
  return CoercionFailed('No entendí si "$raw" es verdadero o falso. Decime sí o no.');
}

CoercionResult _coerceInteger(Object raw) {
  if (raw is int) return Coerced(raw);
  if (raw is double) {
    if (raw == raw.roundToDouble()) return Coerced(raw.round());
    return CoercionFailed('$raw tiene decimales, pero ese campo necesita un número entero.');
  }
  final normalized = _normalizeNumberString(raw.toString());
  if (normalized == null) return CoercionFailed('No pude leer "$raw" como un número.');
  final asDouble = double.tryParse(normalized);
  if (asDouble == null) return CoercionFailed('No pude leer "$raw" como un número.');
  if (asDouble != asDouble.roundToDouble()) {
    return CoercionFailed('$raw tiene decimales, pero ese campo necesita un número entero.');
  }
  return Coerced(asDouble.round());
}

CoercionResult _coerceNumber(Object raw, String? format) {
  if (raw is num) {
    // BigDecimal en el servidor: se manda como String para no perder
    // precisión pasando por double (ver comentario en UapCoerce.java del
    // lado Spring, mismo criterio).
    return Coerced(format == 'decimal' ? raw.toString() : raw.toDouble());
  }
  final normalized = _normalizeNumberString(raw.toString());
  if (normalized == null) {
    return CoercionFailed('No pude leer "$raw" como un número. ¿Podés decirlo de nuevo?');
  }
  final parsed = double.tryParse(normalized);
  if (parsed == null) {
    return CoercionFailed('No pude leer "$raw" como un número. ¿Podés decirlo de nuevo?');
  }
  return Coerced(format == 'decimal' ? normalized : parsed);
}

CoercionResult _coerceString(Object raw, String? format) {
  final s = raw.toString().trim();
  switch (format) {
    case 'date':
      return _coerceDate(s);
    case 'date-time':
      return _coerceDateTime(s);
    default:
      return Coerced(s);
  }
}

final _isoDateRe = RegExp(r'^\d{4}-\d{2}-\d{2}$');
final _slashDateRe = RegExp(r'^(\d{1,2})/(\d{1,2})/(\d{4})$');

CoercionResult _coerceDate(String s) {
  if (_isoDateRe.hasMatch(s)) return Coerced(s);
  final m = _slashDateRe.firstMatch(s);
  if (m != null) {
    final day = m.group(1)!.padLeft(2, '0');
    final month = m.group(2)!.padLeft(2, '0');
    final year = m.group(3)!;
    return Coerced('$year-$month-$day');
  }
  return CoercionFailed('No reconocí "$s" como una fecha. Probá con el formato día/mes/año.');
}

CoercionResult _coerceDateTime(String s) {
  final dateOnly = _coerceDate(s);
  if (dateOnly is Coerced) return Coerced('${dateOnly.value}T00:00:00-04:00');
  try {
    DateTime.parse(s);
    return Coerced(s);
  } catch (_) {
    return CoercionFailed('No reconocí "$s" como una fecha y hora.');
  }
}

/// "25,000" (miles) / "25.000" (miles) / "2500.50" (decimal) / "1,5"
/// (decimal, formato latino) -> string numérico parseable por
/// double.tryParse. Regla: si aparecen AMBOS separadores, el que aparece
/// último es el decimal (formato latino típico "1.234,56"); si aparece
/// uno solo con 1-2 dígitos después, es decimal; con más, es separador de
/// miles y se descarta. Devuelve null si el resultado no es un número
/// válido en absoluto.
String? _normalizeNumberString(String raw) {
  var s = raw.trim();
  final hasComma = s.contains(',');
  final hasDot = s.contains('.');

  if (hasComma && hasDot) {
    if (s.lastIndexOf(',') > s.lastIndexOf('.')) {
      s = s.replaceAll('.', '').replaceAll(',', '.');
    } else {
      s = s.replaceAll(',', '');
    }
  } else if (hasComma) {
    final decimals = s.length - s.lastIndexOf(',') - 1;
    s = decimals <= 2 ? s.replaceAll(',', '.') : s.replaceAll(',', '');
  } else if (hasDot) {
    // Un solo punto: si tiene mas de 2 digitos despues, es separador de
    // miles latino ("25.000" -> 25000), no decimal. double.tryParse ya
    // interpreta "25.000" como 25.0 si no se corrige esto -- justo el bug
    // que este chequeo evita.
    final decimals = s.length - s.lastIndexOf('.') - 1;
    if (decimals > 2) s = s.replaceAll('.', '');
  }

  return double.tryParse(s) != null ? s : null;
}
