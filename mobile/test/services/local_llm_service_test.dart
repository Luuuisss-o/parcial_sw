import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/services/local_llm_service.dart';

void main() {
  group('extractFirstJsonObject', () {
    test('extrae un JSON limpio', () {
      final result = extractFirstJsonObject('{"tool": "create_class", "args": {}}');
      expect(result, '{"tool": "create_class", "args": {}}');
    });

    test('ignora texto antes y despues del JSON', () {
      final result = extractFirstJsonObject('Claro, acá está: {"tool": "list_producto", "args": {}} espero que ayude');
      expect(result, '{"tool": "list_producto", "args": {}}');
    });

    test('maneja bloques de codigo markdown alrededor', () {
      final result = extractFirstJsonObject('```json\n{"tool": "get_cliente", "args": {"id": 1}}\n```');
      expect(result, '{"tool": "get_cliente", "args": {"id": 1}}');
    });

    test('respeta llaves anidadas balanceadas', () {
      final result = extractFirstJsonObject('{"tool": "create_producto", "args": {"nombre": "x", "meta": {"a": 1}}}');
      expect(result, '{"tool": "create_producto", "args": {"nombre": "x", "meta": {"a": 1}}}');
    });

    test('sin ningun JSON devuelve null', () {
      expect(extractFirstJsonObject('no entendí el pedido'), isNull);
    });

    test('JSON incompleto (sin cierre) devuelve null', () {
      expect(extractFirstJsonObject('{"tool": "create_class"'), isNull);
    });
  });

  group('parseToolCallFromRaw', () {
    test('parsea tool y args correctamente', () {
      final call = parseToolCallFromRaw('{"tool": "create_class", "args": {"name": "Cliente"}}');
      expect(call.tool, 'create_class');
      expect(call.arguments['name'], 'Cliente');
    });

    test('sin campo tool lanza FormatException', () {
      expect(() => parseToolCallFromRaw('{"args": {}}'), throwsFormatException);
    });

    test('sin ningun JSON lanza FormatException', () {
      expect(() => parseToolCallFromRaw('no entendí nada'), throwsFormatException);
    });

    test('args ausente se trata como mapa vacio', () {
      final call = parseToolCallFromRaw('{"tool": "list_producto"}');
      expect(call.arguments, isEmpty);
    });
  });

  group('parseLlmResponseFromRaw', () {
    test('un JSON con "tool" se interpreta como ToolProposal', () {
      final r = parseLlmResponseFromRaw('{"tool": "create_producto", "args": {"nombre": "x"}}');
      expect(r, isA<ToolProposal>());
      expect((r as ToolProposal).call.tool, 'create_producto');
      expect(r.call.arguments['nombre'], 'x');
    });

    test('un JSON con "chat" se interpreta como ChatReply', () {
      final r = parseLlmResponseFromRaw('{"chat": "¡Hola! ¿En qué te puedo ayudar?"}');
      expect(r, isA<ChatReply>());
      expect((r as ChatReply).text, '¡Hola! ¿En qué te puedo ayudar?');
    });

    test('ignora texto extra alrededor del JSON, igual que parseToolCallFromRaw', () {
      final r = parseLlmResponseFromRaw('Claro: {"chat": "todo bien"} espero que sirva');
      expect(r, isA<ChatReply>());
      expect((r as ChatReply).text, 'todo bien');
    });

    test('sin "tool" ni "chat" lanza FormatException', () {
      expect(() => parseLlmResponseFromRaw('{"otracosa": 1}'), throwsFormatException);
    });

    test('sin ningun JSON lanza FormatException', () {
      expect(() => parseLlmResponseFromRaw('no entendí nada'), throwsFormatException);
    });

    test('si ambos campos estan presentes, "chat" tiene prioridad', () {
      // No debería pasar en la práctica (el prompt pide uno u otro), pero
      // si el modelo mezcla ambos, se prefiere no ejecutar nada por las
      // dudas -- charlar es siempre la opción más segura.
      final r = parseLlmResponseFromRaw('{"tool": "delete_producto", "args": {"id": 1}, "chat": "no estoy seguro"}');
      expect(r, isA<ChatReply>());
    });
  });
}
