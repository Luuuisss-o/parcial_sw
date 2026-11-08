// Verifica que el prompt que arma la app en el celular sea idéntico al que
// usa training/build_dataset.py para entrenar el modelo personalizado.
// Si este test falla, el modelo se entrenó con otro formato y va a
// responder peor en el teléfono.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/services/assistant_prompt.dart';

void main() {
  // `flutter test` corre con el directorio del paquete (mobile/) como cwd.
  final fixtures = Directory('../training/fixtures');

  test('el mensaje de usuario coincide byte a byte con el del entrenamiento (Python)', () {
    final ctx = jsonDecode(File('${fixtures.path}/context_example.json').readAsStringSync()) as Map<String, dynamic>;
    final expected = File('${fixtures.path}/context_example.expected.txt').readAsStringSync();
    expect(buildTeamAssistantUserMessage(ctx), expected);
  });

  test('plantilla de chat de Gemma: el prompt de sistema va en el primer turno', () {
    final p = formatGemmaChat('SYS', 'USR');
    expect(p, '<start_of_turn>user\nSYS\n\nUSR<end_of_turn>\n<start_of_turn>model\n');
  });

  test('el prompt de sistema define el formato de salida y la regla del nombre', () {
    expect(kTeamAssistantSystemPrompt, contains('{"say":'));
    expect(kTeamAssistantSystemPrompt, contains('por su nombre de pila'));
  });

  group('parseAssistantReply', () {
    test('respuesta de mentoría sin acciones', () {
      final r = parseAssistantReply('{"say": "Ana, un atributo derivado es...", "actions": []}');
      expect(r.say, 'Ana, un atributo derivado es...');
      expect(r.actions, isEmpty);
    });

    test('varias acciones con texto alrededor y bloque ```json', () {
      final r = parseAssistantReply('Claro:\n```json\n{"say": "Bruno, listo {ok}.", "actions": ['
          '{"tool": "create_class", "args": {"name": "Pago"}},'
          '{"tool": "add_attribute", "args": {"class_name": "Pago", "name": "monto", "type": "Double"}}]}\n```');
      expect(r.say, 'Bruno, listo {ok}.');
      expect(r.actions.map((a) => a.tool), ['create_class', 'add_attribute']);
      expect(r.actions[1].args['type'], 'Double');
    });

    test('compatibilidad con los formatos viejos de la app', () {
      expect(parseAssistantReply('{"tool": "create_class", "args": {"name": "X"}}').actions.single.tool, 'create_class');
      expect(parseAssistantReply('{"chat": "hola"}').say, 'hola');
    });

    test('si no hay JSON, el texto se usa como respuesta', () {
      final r = parseAssistantReply('Ana, no entendí.');
      expect(r.say, 'Ana, no entendí.');
      expect(r.actions, isEmpty);
    });
  });
}
