// Notación UML 2.5 en el modelo de la app: se lee tanto con los nombres en
// inglés (eventos en vivo, endpoints de atributos/métodos) como con los
// alias en español (listado de clases y relaciones), y los valores por
// defecto mantienen compatibles los diagramas viejos.
import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/models/diagram.dart';

void main() {
  test('atributo con notación completa (alias en español)', () {
    final a = UmlAttribute.fromJson({
      'id': 'a1',
      'nombre': 'items',
      'tipo': 'string',
      'requerido': false,
      'visibilidad': '#',
      'es_estatico': true,
      'es_derivado': true,
      'multiplicidad': '1..*',
      'valor_inicial': 'vacio',
    });
    expect(a.visibility, '#');
    expect(a.isStatic, isTrue);
    expect(a.umlText, '/items : string [1..*] = vacio');
  });

  test('atributo viejo sin notación usa los valores por defecto', () {
    final a = UmlAttribute.fromJson({'id': 'a2', 'name': 'id', 'type': 'int', 'required': true});
    expect(a.visibility, '-');
    expect(a.isStatic, isFalse);
    expect(a.umlText, 'id : int');
  });

  test('método con parámetros y abstracto', () {
    final m = UmlMethod.fromJson({
      'id': 'm1',
      'name': 'calcularTotal',
      'return_type': 'double',
      'is_abstract': true,
      'params': 'descuento: double',
    });
    expect(m.visibility, '+');
    expect(m.isAbstract, isTrue);
    expect(m.umlText, 'calcularTotal(descuento: double) : double');
  });

  test('tipo de clase', () {
    final c = UmlClass.fromJson({'id': 'c1', 'nombre': 'Pagable', 'tipo_clase': 'interface'});
    expect(c.kind, 'interface');
    final viejo = UmlClass.fromJson({'id': 'c2', 'name': 'Cliente'});
    expect(viejo.kind, 'class');
  });

  test('realización, roles y navegabilidad', () {
    final r = UmlRelation.fromJson({
      'id': 'r1',
      'origen_id': 'c1',
      'destino_id': 'c2',
      'tipo': 'REALIZATION',
      'mult_origen_min': 1,
      'mult_origen_max': 1,
      'mult_destino_min': 1,
      'mult_destino_max': 1,
      'rol_origen': null,
      'navegable_destino': false,
    });
    expect(r.type, RelationType.realization);
    expect(relationTypeToApiString(r.type), 'REALIZATION');

    final a = UmlRelation.fromJson({
      'id': 'r2',
      'from_class': 'c1',
      'to_class': 'c2',
      'type': 'ASSOCIATION',
      'src_role': 'pedidos',
      'dst_navigable': true,
    });
    expect(a.srcRole, 'pedidos');
    expect(a.dstNavigable, isTrue);
    expect(a.srcNavigable, isFalse);
  });
}
