import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/uap/connection_manager.dart';

void main() {
  test('backoffFor sigue la secuencia 1,2,5,10,30 segundos', () {
    expect(backoffFor(0), const Duration(seconds: 1));
    expect(backoffFor(1), const Duration(seconds: 2));
    expect(backoffFor(2), const Duration(seconds: 5));
    expect(backoffFor(3), const Duration(seconds: 10));
    expect(backoffFor(4), const Duration(seconds: 30));
  });

  test('backoffFor se estabiliza en 30s para intentos mas alla del ultimo paso', () {
    expect(backoffFor(5), const Duration(seconds: 30));
    expect(backoffFor(100), const Duration(seconds: 30));
  });

  test('backoffFor con intento negativo no lanza y usa el primer paso', () {
    expect(backoffFor(-1), const Duration(seconds: 1));
  });
}
