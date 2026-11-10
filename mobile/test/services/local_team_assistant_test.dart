import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/services/assistant_prompt.dart';
import 'package:uml_collab_mobile/services/diagram_tool_runner.dart';
import 'package:uml_collab_mobile/services/local_team_assistant.dart';

class _Posted {
  String? content, error, aiMode, label;
  List<Map<String, dynamic>>? actions, proposed;
}

LocalTeamAssistant _assistant({
  required String mode,
  required AssistantReply reply,
  required _Posted posted,
  List<List<AssistantAction>>? ran,
  bool Function(AssistantAction)? fails,
}) =>
    LocalTeamAssistant(
      fetchContext: (_) async => {'mode': mode, 'requester_name': 'Ana Pérez', 'question': 'q'},
      model: (_) async => reply,
      runActions: (actions) async {
        ran?.add(actions);
        return [for (final a in actions) ActionOutcome(a, !(fails?.call(a) ?? false), 'hecho ${a.tool}')];
      },
      postAnswer: (id, {content, error, actions, proposedActions, aiMode, modelLabel}) async {
        posted
          ..content = content
          ..error = error
          ..actions = actions
          ..proposed = proposedActions
          ..aiMode = aiMode
          ..label = modelLabel;
      },
      modelLabel: () => 'Gemma 3 1B personalizado (móvil)',
    );

void main() {
  test('mentoría: nunca ejecuta acciones aunque el modelo las proponga', () async {
    final posted = _Posted();
    final ran = <List<AssistantAction>>[];
    await _assistant(
      mode: 'MENTOR',
      reply: const AssistantReply('Ana, un atributo derivado...', [AssistantAction('delete_class', {'class_name': 'X'})]),
      posted: posted,
      ran: ran,
    ).answer('q1');
    expect(ran, isEmpty);
    expect(posted.aiMode, 'MENTOR');
    expect(posted.content, 'Ana, un atributo derivado...');
    // Lo que propuso como asesor viaja al servidor como propuesta (no se ejecutó).
    expect(posted.proposed, [
      {'tool': 'delete_class', 'args': {'class_name': 'X'}}
    ]);
    expect(posted.label, 'Gemma 3 1B personalizado (móvil)');
  });

  test('edición: ejecuta las acciones y las informa', () async {
    final posted = _Posted();
    await _assistant(
      mode: 'AUTO',
      reply: const AssistantReply('Ana, creé Pago.', [
        AssistantAction('create_class', {'name': 'Pago'}),
        AssistantAction('add_attribute', {'class_name': 'Pago', 'name': 'monto', 'type': 'Double'}),
      ]),
      posted: posted,
    ).answer('q1');
    expect(posted.aiMode, 'AUTO');
    expect(posted.actions!.map((a) => a['tool']), ['create_class', 'add_attribute']);
  });

  test('si una acción falla, la respuesta lo dice (no confirma cambios inexistentes)', () async {
    final posted = _Posted();
    await _assistant(
      mode: 'AUTO',
      reply: const AssistantReply('Ana, listo.', [AssistantAction('add_attribute', {'class_name': 'Nada'})]),
      posted: posted,
      fails: (_) => true,
    ).answer('q1');
    expect(posted.content, startsWith('No pude aplicar los cambios'));
    expect(posted.actions, isEmpty);
  });

  test('respuesta vacía o excepción -> se publica como error', () async {
    final posted = _Posted();
    await _assistant(mode: 'AUTO', reply: const AssistantReply('', []), posted: posted).answer('q1');
    expect(posted.error, isNotNull);

    final p2 = _Posted();
    await LocalTeamAssistant(
      fetchContext: (_) async => throw Exception('sin red'),
      model: (_) async => const AssistantReply('', []),
      runActions: (_) async => [],
      postAnswer: (id, {content, error, actions, proposedActions, aiMode, modelLabel}) async => p2.error = error,
      modelLabel: () => 'm',
    ).answer('q1');
    expect(p2.error, contains('sin red'));
  });

  test('detección de @IA igual que el backend', () {
    expect(mentionsAi('@IA qué es UML?'), isTrue);
    expect(mentionsAi('hola @asistente'), isTrue);
    expect(mentionsAi('mail a ana@ia.com'), isFalse);
    expect(mentionsAi('@iaxyz'), isFalse);
  });

  test('multiplicidades', () {
    expect(parseMultiplicity('1'), (1, 1));
    expect(parseMultiplicity('0..*'), (0, null));
    expect(parseMultiplicity('1..*'), (1, null));
    expect(parseMultiplicity('*'), (0, null));
    expect(parseMultiplicity('2..5'), (2, 5));
  });

  group('confirmación de eliminaciones (misma regla que el servidor)', () {
    const diagram = {
      'clases': [
        {'nombre': 'Cliente', 'atributos': [{'nombre': 'email', 'tipo': 'String'}], 'metodos': []},
        {'nombre': 'Temporal', 'atributos': [], 'metodos': []},
      ],
      'relaciones': [
        {'origen': 'Cliente', 'destino': 'Pedido', 'tipo': 'ASSOCIATION'},
      ],
    };
    const borrarCliente = [AssistantAction('delete_class', {'class_name': 'Cliente'})];

    test('borrar una clase con contenido sin confirmar: pregunta y dice qué se pierde', () {
      final ask = destructiveConfirmationNeeded(borrarCliente, diagram, 'eliminá Cliente', requester: 'Ana');
      expect(ask, contains('Ana, eliminar la clase Cliente borra también 1 atributo(s), 1 relación(es)'));
      expect(ask, contains('@IA confirmo'));
    });

    test('con confirmación explícita se ejecuta', () {
      expect(destructiveConfirmationNeeded(borrarCliente, diagram, 'confirmo, eliminá Cliente'), isNull);
      expect(destructiveConfirmationNeeded(borrarCliente, diagram, '@IA sí, borrala'), isNull);
    });

    test('"si eliminás X, ¿qué pasa?" no cuenta como confirmación', () {
      expect(destructiveConfirmationNeeded(borrarCliente, diagram, 'si eliminás Cliente, ¿qué pasa?'), isNotNull);
    });

    test('una clase vacía o un atributo suelto se borran directo', () {
      expect(destructiveConfirmationNeeded(
          const [AssistantAction('delete_class', {'class_name': 'Temporal'})], diagram, 'borrá Temporal'), isNull);
      expect(destructiveConfirmationNeeded(
          const [AssistantAction('delete_attribute', {'class_name': 'Cliente', 'attribute_name': 'email'})],
          diagram, 'borrá email'), isNull);
    });

    test('varias eliminaciones juntas piden confirmación', () {
      final ask = destructiveConfirmationNeeded(const [
        AssistantAction('delete_attribute', {'class_name': 'Cliente', 'attribute_name': 'email'}),
        AssistantAction('delete_class', {'class_name': 'Temporal'}),
      ], diagram, 'borrá email y Temporal');
      expect(ask, contains('2 eliminaciones'));
    });

    test('el asistente del chat no ejecuta y publica la pregunta', () async {
      final posted = _Posted();
      final ran = <List<AssistantAction>>[];
      await LocalTeamAssistant(
        fetchContext: (_) async => {
          'mode': 'AUTO', 'requester_name': 'Ana', 'question': 'eliminá Cliente', 'diagram': diagram,
        },
        model: (_) async => const AssistantReply('Ana, eliminé Cliente.', borrarCliente),
        runActions: (a) async {
          ran.add(a);
          return const [];
        },
        postAnswer: (id, {content, error, actions, proposedActions, aiMode, modelLabel}) async {
          posted
            ..content = content
            ..actions = actions;
        },
        modelLabel: () => 'm',
      ).answer('q');
      expect(ran, isEmpty);
      expect(posted.content, contains('No la eliminé todavía'));
      expect(posted.actions, isEmpty);
    });
  });
}
