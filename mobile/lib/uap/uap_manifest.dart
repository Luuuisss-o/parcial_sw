// lib/uap/uap_manifest.dart
//
// Modelos del contrato UAP descubierto en runtime contra un backend Spring
// Boot generado (ver exporters/generators/uap_generator.py del lado
// Python que lo genera). A diferencia de lib/models/diagram.dart (que
// modela el dominio FIJO del diagramador: Diagram/UmlClass/etc), acá el
// dominio es arbitrario -- lo único fijo es la FORMA del contrato
// (entidades con alias, tools con inputSchema), nunca los nombres de
// entidad concretos.

class UapEntity {
  final String key;
  final String label;
  final String plural;
  final List<String> aliases;
  final String idType;

  UapEntity({
    required this.key,
    required this.label,
    required this.plural,
    required this.aliases,
    required this.idType,
  });

  factory UapEntity.fromJson(Map<String, dynamic> json) {
    return UapEntity(
      key: json['key'] as String,
      label: json['label'] as String? ?? json['key'] as String,
      plural: json['plural'] as String? ?? '${json['key']}s',
      aliases: (json['aliases'] as List?)?.map((a) => a.toString()).toList() ?? [json['key'].toString()],
      idType: json['idType'] as String? ?? 'long',
    );
  }
}

class UapManifest {
  final String uapVersion;
  final String backendName;
  final String generation;
  final String timezone;
  final List<UapEntity> entities;

  UapManifest({
    required this.uapVersion,
    required this.backendName,
    required this.generation,
    required this.timezone,
    required this.entities,
  });

  factory UapManifest.fromJson(Map<String, dynamic> json) {
    return UapManifest(
      uapVersion: json['uapVersion'] as String? ?? '1.0',
      backendName: json['backendName'] as String? ?? '',
      generation: json['generation'] as String? ?? '',
      timezone: json['timezone'] as String? ?? 'America/La_Paz',
      entities: (json['entities'] as List? ?? [])
          .map((e) => UapEntity.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// Un campo del inputSchema de una tool: no se modela como JSON-Schema
/// genérico completo (sería sobre-ingeniería para lo que el generador del
/// lado Python realmente produce hoy) -- alcanza con type/format, que es
/// justo lo que type_coercion.dart necesita para decidir cómo convertir un
/// valor crudo.
class UapFieldSchema {
  final String type; // "string" | "integer" | "number" | "boolean"
  final String? format; // "date" | "date-time" | "decimal" | "int32" | "int64" | null

  UapFieldSchema({required this.type, this.format});

  factory UapFieldSchema.fromJson(Map<String, dynamic> json) {
    return UapFieldSchema(type: json['type'] as String? ?? 'string', format: json['format'] as String?);
  }
}

class UapTool {
  final String toolId;
  final String entityKey;
  final String description;
  final Map<String, UapFieldSchema> properties;
  final List<String> required;

  UapTool({
    required this.toolId,
    required this.entityKey,
    required this.description,
    required this.properties,
    required this.required,
  });

  factory UapTool.fromJson(Map<String, dynamic> json) {
    final inputSchema = json['inputSchema'] as Map<String, dynamic>? ?? {};
    final rawProps = inputSchema['properties'] as Map<String, dynamic>? ?? {};
    return UapTool(
      toolId: json['toolId'] as String,
      entityKey: json['entity'] as String? ?? '',
      description: json['description'] as String? ?? '',
      properties: rawProps.map((k, v) => MapEntry(k, UapFieldSchema.fromJson(v as Map<String, dynamic>))),
      required: (inputSchema['required'] as List? ?? []).map((r) => r.toString()).toList(),
    );
  }

  /// El verbo CRUD que esta tool representa (create/list/get/update/
  /// delete), extraído del propio toolId ("create_producto" -> "create").
  /// El generador siempre produce toolIds con ese patrón exacto (ver
  /// uap_generator.py::_tool_id), así que confiar en el patrón en vez de
  /// pedirle al backend un campo aparte es seguro.
  String get verb => toolId.split('_').first;
}

/// El contrato completo descubierto contra un backend: manifest + tools
/// indexadas por toolId + entidades indexadas por CUALQUIER alias
/// conocido (para que el parser pueda resolver "producto" o "productos"
/// sin tener que decidir de antemano cuál es la forma canónica).
class UapContract {
  final UapManifest manifest;
  final List<UapTool> tools;

  UapContract({required this.manifest, required this.tools});

  late final Map<String, UapTool> toolsById = {for (final t in tools) t.toolId: t};

  late final Map<String, UapEntity> entitiesByAlias = {
    for (final e in manifest.entities)
      for (final alias in e.aliases) alias.toLowerCase(): e,
  };

  UapTool? toolFor(String verb, String entityKey) => toolsById['${verb}_$entityKey'];
}
