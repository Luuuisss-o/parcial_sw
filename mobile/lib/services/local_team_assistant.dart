// lib/services/local_team_assistant.dart
//
// Responde en el CELULAR una consulta "@IA" del chat del equipo, con el
// modelo personalizado que corre localmente (Fase 2). Mismo comportamiento
// que el asistente del servidor:
//
//   1. Pide el contexto de la consulta (memoria híbrida: diagrama, equipo,
//      hilo propio) -> GET /chat/{id}/context.
//   2. El modelo local propone {"say", "actions"}.
//   3. Si la consulta es teórica (modo MENTOR) se ignora cualquier acción:
//      la mentoría nunca modifica el diagrama, aunque el modelo chico se
//      equivoque y proponga alguna.
//   4. Ejecuta las acciones con la API REST (se difunden a todos).
//   5. Publica la respuesta en el chat -> POST /chat/{id}/answer: queda
//      dirigida a quien preguntó y visible para todo el equipo. Si alguna
//      acción falló, se dice explícitamente (nunca se confirma un cambio que
//      no se hizo).
//
// Las dependencias se inyectan como funciones para poder testear el flujo
// sin un modelo real ni un servidor (test/services/local_team_assistant_test.dart).

import 'assistant_prompt.dart';
import 'diagram_tool_runner.dart';

typedef ContextFetcher = Future<Map<String, dynamic>> Function(String questionId);
typedef ModelAnswer = Future<AssistantReply> Function(Map<String, dynamic> context);
typedef ActionsRunner = Future<List<ActionOutcome>> Function(List<AssistantAction> actions);
typedef AnswerPoster = Future<void> Function(
  String questionId, {
  String? content,
  String? error,
  List<Map<String, dynamic>>? actions,
  String? aiMode,
  String? modelLabel,
});

/// Tope de acciones por respuesta: el modelo chico a veces entra en bucle
/// repitiendo la misma acción; con la entrega de soluciones activada una
/// solución acotada (3-6 clases con atributos y relaciones) entra holgada.
const int kMaxActionsPerAnswer = 40;

class LocalTeamAssistant {
  final ContextFetcher fetchContext;
  final ModelAnswer model;
  final ActionsRunner runActions;
  final AnswerPoster postAnswer;
  final String Function() modelLabel;

  LocalTeamAssistant({
    required this.fetchContext,
    required this.model,
    required this.runActions,
    required this.postAnswer,
    required this.modelLabel,
  });

  Future<void> answer(String questionId) async {
    try {
      final ctx = await fetchContext(questionId);
      final reply = await model(ctx);
      final mentor = ctx['mode'] == 'MENTOR';

      var actions = mentor ? const <AssistantAction>[] : reply.actions;
      if (actions.length > kMaxActionsPerAnswer) actions = actions.sublist(0, kMaxActionsPerAnswer);
      final outcomes = actions.isEmpty ? const <ActionOutcome>[] : await runActions(actions);

      final failed = outcomes.where((o) => !o.ok).toList();
      final done = outcomes.where((o) => o.ok).toList();
      var say = reply.say.trim();
      if (say.isEmpty && done.isNotEmpty) say = done.map((o) => o.message).join(' ');
      if (failed.isNotEmpty) {
        final nota = failed.map((o) => '- ${o.message}').join('\n');
        say = done.isEmpty
            ? 'No pude aplicar los cambios en el diagrama:\n$nota'
            : '$say\n\nNo pude aplicar todo:\n$nota';
      }
      if (say.isEmpty) {
        await postAnswer(questionId, error: 'El modelo local no generó una respuesta.', modelLabel: modelLabel());
        return;
      }
      await postAnswer(
        questionId,
        content: say,
        actions: done.map((o) => o.toJson()).toList(),
        aiMode: (mentor || actions.isEmpty) && done.isEmpty ? 'MENTOR' : 'AUTO',
        modelLabel: modelLabel(),
      );
    } catch (e) {
      await postAnswer(questionId, error: 'El modelo local del celular falló: $e', modelLabel: modelLabel());
    }
  }
}

/// Misma detección de "@IA" que el backend (chat_service._AI_MENTION_RE).
final RegExp kAiMentionRe = RegExp(r'(?<![\w@.])@(?:ia|ai|asistente)\b', caseSensitive: false);
bool mentionsAi(String text) => kAiMentionRe.hasMatch(text);
