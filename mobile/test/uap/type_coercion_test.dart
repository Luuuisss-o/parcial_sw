import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/uap/type_coercion.dart';

void main() {
  group('coerce boolean', () {
    for (final word in ['true', '1', 'si', 'sí', 'verdadero', 'activo']) {
      test('"$word" -> true', () {
        final r = coerce(declaredType: 'boolean', raw: word);
        expect(r, isA<Coerced>());
        expect((r as Coerced).value, true);
      });
    }
    for (final word in ['false', '0', 'no', 'falso', 'inactivo']) {
      test('"$word" -> false', () {
        final r = coerce(declaredType: 'boolean', raw: word);
        expect(r, isA<Coerced>());
        expect((r as Coerced).value, false);
      });
    }
    test('valor no reconocido falla con mensaje en español', () {
      final r = coerce(declaredType: 'boolean', raw: 'tal vez');
      expect(r, isA<CoercionFailed>());
      expect((r as CoercionFailed).messageEs, contains('verdadero o falso'));
    });
    test('bool nativo de Dart pasa directo', () {
      final r = coerce(declaredType: 'boolean', raw: true);
      expect((r as Coerced).value, true);
    });
  });

  group('coerce integer', () {
    test('string entero simple', () {
      final r = coerce(declaredType: 'integer', raw: '25000');
      expect((r as Coerced).value, 25000);
    });
    test('con separador de miles coma', () {
      final r = coerce(declaredType: 'integer', raw: '25,000');
      expect((r as Coerced).value, 25000);
    });
    test('con separador de miles punto', () {
      final r = coerce(declaredType: 'integer', raw: '25.000');
      expect((r as Coerced).value, 25000);
    });
    test('int nativo pasa directo', () {
      final r = coerce(declaredType: 'integer', raw: 2500);
      expect((r as Coerced).value, 2500);
    });
    test('con decimales no nulos falla', () {
      final r = coerce(declaredType: 'integer', raw: '3.5');
      expect(r, isA<CoercionFailed>());
      expect((r as CoercionFailed).messageEs, contains('entero'));
    });
    test('no numerico falla', () {
      final r = coerce(declaredType: 'integer', raw: 'barato');
      expect(r, isA<CoercionFailed>());
    });
  });

  group('coerce number', () {
    test('decimal simple sin format', () {
      final r = coerce(declaredType: 'number', raw: '2500.50');
      expect((r as Coerced).value, 2500.50);
    });
    test('formato latino con miles y decimal: 1.234,56 -> 1234.56', () {
      final r = coerce(declaredType: 'number', raw: '1.234,56');
      expect((r as Coerced).value, 1234.56);
    });
    test('coma como decimal: 1,5 -> 1.5', () {
      final r = coerce(declaredType: 'number', raw: '1,5');
      expect((r as Coerced).value, 1.5);
    });
    test('coma como miles (mas de 2 digitos): 1,234 -> 1234', () {
      final r = coerce(declaredType: 'number', raw: '1,234');
      expect((r as Coerced).value, 1234.0);
    });
    test('format decimal devuelve String, no double (precision BigDecimal)', () {
      final r = coerce(declaredType: 'number', format: 'decimal', raw: '2500.50');
      expect((r as Coerced).value, isA<String>());
      expect(r.value, '2500.50');
    });
    test('no numerico falla con mensaje en español', () {
      final r = coerce(declaredType: 'number', raw: 'barato');
      expect(r, isA<CoercionFailed>());
      expect((r as CoercionFailed).messageEs, contains('número'));
    });
  });

  group('coerce string con formato date', () {
    test('ya en ISO pasa igual', () {
      final r = coerce(declaredType: 'string', format: 'date', raw: '2025-03-15');
      expect((r as Coerced).value, '2025-03-15');
    });
    test('dd/MM/yyyy se convierte a ISO', () {
      final r = coerce(declaredType: 'string', format: 'date', raw: '15/03/2025');
      expect((r as Coerced).value, '2025-03-15');
    });
    test('fecha invalida falla', () {
      final r = coerce(declaredType: 'string', format: 'date', raw: 'ayer');
      expect(r, isA<CoercionFailed>());
    });
  });

  group('coerce string plano', () {
    test('sin formato especial, pasa tal cual (trim)', () {
      final r = coerce(declaredType: 'string', raw: '  Martillo  ');
      expect((r as Coerced).value, 'Martillo');
    });
  });

  test('coerce nunca lanza excepciones', () {
    final inputs = [null, '', 'x' * 500, 123, true, [], {}];
    for (final input in inputs) {
      for (final type in ['boolean', 'integer', 'number', 'string']) {
        expect(() => coerce(declaredType: type, raw: input), returnsNormally);
      }
    }
  });
}
