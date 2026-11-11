// lib/models/diagram.dart
//
// Modelos de datos, espejo exacto de los schemas Pydantic del backend
// (backend/app/schemas/*.py). Los nombres de campo son los mismos que
// devuelve la API en JSON.

class Diagram {
  final String id;
  final String title;
  final DateTime updatedAt;
  final int ownerId;
  final String ownerEmail;

  Diagram({
    required this.id,
    required this.title,
    required this.updatedAt,
    required this.ownerId,
    required this.ownerEmail,
  });

  factory Diagram.fromJson(Map<String, dynamic> json) => Diagram(
        id: json['id'] as String,
        title: json['title'] as String,
        updatedAt: DateTime.parse(json['updated_at'] as String),
        ownerId: json['owner_id'] as int,
        ownerEmail: json['owner_email'] as String,
      );
}

class UmlAttribute {
  final String id;
  final String name;
  final String type;
  final bool required;
  // Notación UML 2.5
  final String visibility; // + - # ~
  final bool isStatic;
  final bool isDerived;
  final String? multiplicity;
  final String? defaultValue;

  UmlAttribute({
    required this.id,
    required this.name,
    required this.type,
    required this.required,
    this.visibility = '-',
    this.isStatic = false,
    this.isDerived = false,
    this.multiplicity,
    this.defaultValue,
  });

  /// `[/]nombre : tipo [mult] [= valor]` (sin la visibilidad).
  String get umlText {
    final b = StringBuffer('${isDerived ? '/' : ''}$name : $type');
    if (multiplicity != null && multiplicity!.isNotEmpty) b.write(' [$multiplicity]');
    if (defaultValue != null && defaultValue!.isNotEmpty) b.write(' = $defaultValue');
    return b.toString();
  }

  factory UmlAttribute.fromJson(Map<String, dynamic> json) => UmlAttribute(
        id: json['id'] as String,
        name: (json['name'] ?? json['nombre']) as String,
        type: (json['type'] ?? json['tipo']) as String,
        required: (json['required'] ?? json['requerido']) as bool,
        visibility: (json['visibility'] ?? json['visibilidad'] ?? '-') as String,
        isStatic: (json['is_static'] ?? json['es_estatico'] ?? false) as bool,
        isDerived: (json['is_derived'] ?? json['es_derivado'] ?? false) as bool,
        multiplicity: (json['multiplicity'] ?? json['multiplicidad']) as String?,
        defaultValue: (json['default_value'] ?? json['valor_inicial']) as String?,
      );
}

class UmlMethod {
  final String id;
  final String name;
  final String returnType;
  // Notación UML 2.5
  final String visibility;
  final bool isStatic;
  final bool isAbstract;
  final String params;

  UmlMethod({
    required this.id,
    required this.name,
    required this.returnType,
    this.visibility = '+',
    this.isStatic = false,
    this.isAbstract = false,
    this.params = '',
  });

  /// `nombre(parámetros) : tipo` (sin la visibilidad).
  String get umlText => '$name($params) : $returnType';

  factory UmlMethod.fromJson(Map<String, dynamic> json) => UmlMethod(
        id: json['id'] as String,
        name: (json['name'] ?? json['nombre']) as String,
        returnType: (json['return_type'] ?? json['tipo_retorno']) as String,
        visibility: (json['visibility'] ?? json['visibilidad'] ?? '+') as String,
        isStatic: (json['is_static'] ?? json['es_estatico'] ?? false) as bool,
        isAbstract: (json['is_abstract'] ?? json['es_abstracto'] ?? false) as bool,
        params: (json['params'] ?? json['parametros'] ?? '') as String,
      );
}

class UmlClass {
  final String id;
  final String name;
  /// UML 2.5: class | abstract | interface | enumeration
  final String kind;
  final int xGrid;
  final int yGrid;
  final int wGrid;
  final int hGrid;
  final int zIndex;
  final List<UmlAttribute> attributes;
  final List<UmlMethod> methods;

  UmlClass({
    required this.id,
    required this.name,
    this.kind = 'class',
    required this.xGrid,
    required this.yGrid,
    required this.wGrid,
    required this.hGrid,
    required this.zIndex,
    this.attributes = const [],
    this.methods = const [],
  });

  UmlClass copyWith({
    String? name,
    int? xGrid,
    int? yGrid,
    int? wGrid,
    int? hGrid,
    List<UmlAttribute>? attributes,
    List<UmlMethod>? methods,
  }) =>
      UmlClass(
        id: id,
        name: name ?? this.name,
        kind: kind,
        xGrid: xGrid ?? this.xGrid,
        yGrid: yGrid ?? this.yGrid,
        wGrid: wGrid ?? this.wGrid,
        hGrid: hGrid ?? this.hGrid,
        zIndex: zIndex,
        attributes: attributes ?? this.attributes,
        methods: methods ?? this.methods,
      );

  factory UmlClass.fromJson(Map<String, dynamic> json) => UmlClass(
        id: json['id'] as String,
        name: (json['name'] ?? json['nombre']) as String,
        kind: (json['kind'] ?? json['tipo_clase'] ?? 'class') as String,
        xGrid: (json['x_grid'] ?? 0) as int,
        yGrid: (json['y_grid'] ?? 0) as int,
        wGrid: (json['w_grid'] ?? 12) as int,
        hGrid: (json['h_grid'] ?? 6) as int,
        zIndex: (json['z_index'] ?? 0) as int,
        attributes: ((json['atributos'] ?? json['attributes'] ?? []) as List)
            .map((a) => UmlAttribute.fromJson(a as Map<String, dynamic>))
            .toList(),
        methods: ((json['metodos'] ?? json['methods'] ?? []) as List)
            .map((m) => UmlMethod.fromJson(m as Map<String, dynamic>))
            .toList(),
      );
}

/// Tipos de relación UML 2.5 soportados (los mismos del backend y del
/// editor web: no hay que inventar notación nueva, solo dibujarla en móvil).
enum RelationType { association, aggregation, composition, inheritance, dependency, realization }

RelationType relationTypeFromString(String s) {
  switch (s.toUpperCase()) {
    case 'AGGREGATION':
      return RelationType.aggregation;
    case 'COMPOSITION':
      return RelationType.composition;
    case 'INHERITANCE':
    case 'GENERALIZATION':
      return RelationType.inheritance;
    case 'DEPENDENCY':
      return RelationType.dependency;
    case 'REALIZATION':
      return RelationType.realization;
    default:
      return RelationType.association;
  }
}

String relationTypeToApiString(RelationType t) {
  switch (t) {
    case RelationType.aggregation:
      return 'AGGREGATION';
    case RelationType.composition:
      return 'COMPOSITION';
    case RelationType.inheritance:
      return 'INHERITANCE';
    case RelationType.dependency:
      return 'DEPENDENCY';
    case RelationType.realization:
      return 'REALIZATION';
    case RelationType.association:
      return 'ASSOCIATION';
  }
}

class UmlRelation {
  final String id;
  final String fromClassId;
  final String toClassId;
  final RelationType type;
  final String? label;
  final int srcMultMin;
  final int? srcMultMax; // null = "*"
  final int dstMultMin;
  final int? dstMultMax;
  final String originName;
  final String destinationName;
  // UML 2.5: rol y navegabilidad de cada extremo
  final String? srcRole;
  final String? dstRole;
  final bool srcNavigable;
  final bool dstNavigable;

  UmlRelation({
    required this.id,
    required this.fromClassId,
    required this.toClassId,
    required this.type,
    this.label,
    required this.srcMultMin,
    this.srcMultMax,
    required this.dstMultMin,
    this.dstMultMax,
    required this.originName,
    required this.destinationName,
    this.srcRole,
    this.dstRole,
    this.srcNavigable = false,
    this.dstNavigable = false,
  });

  factory UmlRelation.fromJson(Map<String, dynamic> json) {
    int? parseMax(dynamic v) {
      if (v == null || v == '*') return null;
      return v as int;
    }

    // El backend devuelve nombres en inglés al CREAR (from_class, type...) y
    // en español al LISTAR (origen_id, tipo, mult_origen_min...) -- ver
    // CONTEXTO_PROYECTO.md, sección 12. Se aceptan los dos, igual que el
    // frontend web (antes listRelations fallaba con "Null is not a String").
    return UmlRelation(
      id: json['id'] as String,
      fromClassId: (json['from_class'] ?? json['origen_id']) as String,
      toClassId: (json['to_class'] ?? json['destino_id']) as String,
      type: relationTypeFromString((json['type'] ?? json['tipo']) as String),
      label: (json['label'] ?? json['etiqueta']) as String?,
      srcMultMin: (json['src_mult_min'] ?? json['mult_origen_min'] ?? 1) as int,
      srcMultMax: parseMax(json['src_mult_max'] ?? json['mult_origen_max']),
      dstMultMin: (json['dst_mult_min'] ?? json['mult_destino_min'] ?? 1) as int,
      dstMultMax: parseMax(json['dst_mult_max'] ?? json['mult_destino_max']),
      originName: (json['origen_nombre'] ?? '') as String,
      destinationName: (json['destino_nombre'] ?? '') as String,
      srcRole: (json['src_role'] ?? json['rol_origen']) as String?,
      dstRole: (json['dst_role'] ?? json['rol_destino']) as String?,
      srcNavigable: (json['src_navigable'] ?? json['navegable_origen'] ?? false) as bool,
      dstNavigable: (json['dst_navigable'] ?? json['navegable_destino'] ?? false) as bool,
    );
  }
}

/// Colaborador de un diagrama (owner_email == mío en la app usa este dato
/// para saber si puedo invitar/quitar gente).
class Collaborator {
  final String id;
  final int userId;
  final String email;
  final String name;
  final String role;

  Collaborator({
    required this.id,
    required this.userId,
    required this.email,
    required this.name,
    required this.role,
  });

  factory Collaborator.fromJson(Map<String, dynamic> json) => Collaborator(
        id: json['id'] as String,
        userId: json['user_id'] as int,
        email: json['email'] as String,
        name: json['name'] as String,
        role: json['role'] as String,
      );
}
