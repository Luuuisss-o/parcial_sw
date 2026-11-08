import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/uap/intent_parser.dart';
import 'package:uml_collab_mobile/uap/response_phrasing.dart';
import 'package:uml_collab_mobile/uap/uap_manifest.dart';

UapEntity _producto() =>
    UapEntity(key: 'producto', label: 'Producto', plural: 'productos', aliases: ['producto', 'productos'], idType: 'long');

void main() {
  group('phraseForResult', () {
    test('create con nombre visible', () {
      final phrase = phraseForResult(
        verb: 'create',
        entity: _producto(),
        result: {'producto': {'id': 1, 'nombre': 'Martillo'}},
      );
      expect(phrase, contains('registré'));
      expect(phrase, contains('Martillo'));
    });

    test('list vacio', () {
      final phrase = phraseForResult(verb: 'list', entity: _producto(), result: {'productos': []});
      expect(phrase, contains('No hay productos'));
    });

    test('list con items enumera hasta 5 y resume el resto', () {
      final items = List.generate(7, (i) => {'id': i, 'nombre': 'Producto $i'});
      final phrase = phraseForResult(verb: 'list', entity: _producto(), result: {'productos': items});
      expect(phrase, contains('Encontré 7 productos'));
      expect(phrase, contains('y 2 más'));
    });

    test('update generico', () {
      final phrase = phraseForResult(verb: 'update', entity: _producto(), result: {});
      expect(phrase, contains('Actualicé'));
    });

    test('delete generico', () {
      final phrase = phraseForResult(verb: 'delete', entity: _producto(), result: {});
      expect(phrase, contains('Eliminé'));
    });

    test('offline nunca afirma que se sincronizo con el servidor', () {
      final phrase = phraseForResult(verb: 'create', entity: _producto(), result: {}, offline: true);
      expect(phrase, isNot(contains('en el servidor')));
      expect(phrase, contains('conexión'));
    });
  });

  group('mensajes de estado', () {
    test('cancelado', () {
      expect(phraseForCancelled(), contains('cancelada'));
    });

    test('rechazado por el backend incluye el detalle', () {
      expect(phraseForBackendRejected('campo desconocido: x'), contains('campo desconocido: x'));
    });

    test('conflicto', () {
      expect(phraseForConflict(), contains('conflicto'));
    });
  });

  group('phraseForParseResult', () {
    test('NeedsClarification devuelve su propia pregunta', () {
      final r = NeedsClarification('¿Qué precio le pongo?');
      expect(phraseForParseResult(r), '¿Qué precio le pongo?');
    });

    test('Rejected antepone que no se pudo determinar una accion', () {
      final r = Rejected('esa entidad no existe');
      expect(phraseForParseResult(r), contains('No pude determinar una única acción'));
    });
  });
}
