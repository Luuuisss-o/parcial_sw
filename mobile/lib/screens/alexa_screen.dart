// lib/screens/alexa_screen.dart
//
// Modo "Alexa": solo un botón grande de micrófono y estados -- sin campo
// de texto ni botón de enviar. El flujo es enteramente por voz: Vosk
// (STT, ya integrado) escucha, el LLM local + parser determinista
// interpretan, y la respuesta se lee con TextToSpeech nativo (ver
// lib/voice/tts_service.dart), manteniendo también el texto visible por
// si el usuario prefiere leerlo.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../app_state.dart';
import '../services/local_llm_service.dart';
import '../uap/intent_parser.dart';
import '../uap/response_phrasing.dart';

const _uuid = Uuid();

enum _AlexaStage {
  preparando,
  idle,
  escuchando,
  interpretando,
  validando,
  esperandoConfirmacion,
  sincronizando,
  error,
}

class AlexaScreen extends StatefulWidget {
  const AlexaScreen({super.key});

  @override
  State<AlexaScreen> createState() => _AlexaScreenState();
}

class _AlexaScreenState extends State<AlexaScreen> {
  _AlexaStage _stage = _AlexaStage.preparando;
  String _lastResponse = '';
  bool _spanishVoiceMissing = false;
  String _prepareLabel = 'Preparando el asistente...';
  // Ver el mismo campo en historial_screen.dart: recuerda entidad/verbo
  // a mitad de camino entre un turno de voz y el siguiente.
  ConversationContext _pendingContext = const ConversationContext();

  @override
  void initState() {
    super.initState();
    _prepare();
  }

  /// Carga Vosk (reconocimiento de voz) y el LLM local antes de habilitar
  /// el micrófono -- sin esto, tocar el botón lanzaba "Bad state: El
  /// reconocimiento de voz todavía no está cargado" (Vosk) o fallaba en
  /// silencio al intentar interpretar (LLM), porque ninguno de los dos
  /// llega cargado por defecto: cargarlos es costoso (~1GB en RAM) y no
  /// tiene sentido hacerlo hasta que el usuario realmente entra a este
  /// modo.
  Future<void> _prepare() async {
    final app = context.read<AppState>();
    try {
      final hasSpanish = await app.tts.isSpanishVoiceAvailable();
      if (mounted) setState(() => _spanishVoiceMissing = !hasSpanish);

      if (!app.speech.isReady) {
        if (!await app.downloader.isVoskDownloaded()) {
          setState(() => _prepareLabel = 'Descargando modelo de voz en español (una sola vez)...');
          await app.downloader.downloadVosk(onProgress: (_) {});
        }
        setState(() => _prepareLabel = 'Cargando reconocimiento de voz...');
        await app.speech.load(await app.downloader.voskModelPath());
      }

      if (!app.llm.isLoaded) {
        setState(() => _prepareLabel = 'Cargando el modelo de lenguaje (puede tardar un momento)...');
        await app.downloader.ensureLlmModel(onProgress: (_) {});
        await app.llm.load(await app.downloader.llmModelPath());
      }

      if (mounted) setState(() => _stage = _AlexaStage.idle);
    } catch (e) {
      if (mounted) {
        setState(() {
          _stage = _AlexaStage.error;
          _lastResponse = 'No pude preparar el asistente: $e';
        });
      }
    }
  }

  Future<void> _toggleListening() async {
    final app = context.read<AppState>();
    if (_stage == _AlexaStage.escuchando) {
      await app.speech.stopListening();
      return;
    }
    if (_stage == _AlexaStage.preparando) return;

    setState(() {
      _stage = _AlexaStage.escuchando;
      _lastResponse = '';
    });

    try {
      await app.speech.startListening(
        onPartial: (_) {},
        onFinal: (text) => _handleRecognized(text),
      );
    } catch (e) {
      setState(() {
        _stage = _AlexaStage.error;
        _lastResponse = 'No pude usar el micrófono: $e';
      });
    }
  }

  Future<void> _handleRecognized(String text) async {
    final app = context.read<AppState>();
    await app.speech.stopListening();
    setState(() => _stage = _AlexaStage.interpretando);

    final contract = app.contract;
    if (contract == null) {
      await _respond('Todavía no me conecté a ningún sistema.');
      return;
    }

    LlmDraft? draft;
    try {
      final llmResponse = await app.llm.resolveUapCommand(
        userText: text,
        tools: contract.tools
            .map((t) => UapToolSummary(toolId: t.toolId, description: t.description, fieldNames: t.properties.keys.toList()))
            .toList(),
      );
      switch (llmResponse) {
        case ChatReply(:final text):
          // El LLM ya determinó que esto es charla, no una operación: se
          // lee tal cual, sin pasar por el parser determinista.
          await _respond(text);
          return;
        case ToolProposal(:final call):
          draft = LlmDraft(fields: call.arguments);
      }
    } catch (_) {
      draft = null;
    }

    setState(() => _stage = _AlexaStage.validando);
    final parser = IntentParser(contract);
    final result = parser.parse(text, draft: draft, previous: _pendingContext);

    switch (result) {
      case ParsedInvocation(:final toolId, :final input):
        setState(() => _stage = _AlexaStage.sincronizando);
        _pendingContext = const ConversationContext();
        try {
          final tool = contract.toolsById[toolId]!;
          final entity = contract.manifest.entities.firstWhere((e) => e.key == tool.entityKey);
          final response = await app.uapClient!.invoke(toolId, input, clientRecordId: _uuid.v4());
          await _respond(phraseForResult(verb: tool.verb, entity: entity, result: response));
        } catch (e) {
          await _respond(phraseForBackendRejected(e.toString()));
        }
      case NeedsClarification(:final questionEs, :final context):
        setState(() => _stage = _AlexaStage.esperandoConfirmacion);
        _pendingContext = context;
        await _respond(questionEs);
      case Conversational(:final replyEs):
        await _respond(replyEs);
      case Rejected(:final reasonEs):
        _pendingContext = const ConversationContext();
        await _respond('No pude determinar una única acción: $reasonEs');
    }
  }

  Future<void> _respond(String text) async {
    final app = context.read<AppState>();
    setState(() {
      _lastResponse = text;
      _stage = _AlexaStage.idle;
    });
    await app.tts.speak(text);
  }

  String get _stageLabel => switch (_stage) {
        _AlexaStage.preparando => _prepareLabel,
        _AlexaStage.idle => 'Tocá el micrófono para hablar',
        _AlexaStage.escuchando => 'Escuchando...',
        _AlexaStage.interpretando => 'Interpretando...',
        _AlexaStage.validando => 'Validando...',
        _AlexaStage.esperandoConfirmacion => 'Esperando tu confirmación',
        _AlexaStage.sincronizando => 'Sincronizando...',
        _AlexaStage.error => 'Ocurrió un problema',
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Asistente por voz')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_spanishVoiceMissing)
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text('No encontré una voz en español instalada en este teléfono. Vas a ver la respuesta escrita, pero no la voy a poder leer en voz alta.'),
                ),
              ),
            const Spacer(),
            Center(
              child: GestureDetector(
                onTap: _stage == _AlexaStage.preparando ? null : _toggleListening,
                child: CircleAvatar(
                  radius: 64,
                  backgroundColor: _stage == _AlexaStage.preparando
                      ? Theme.of(context).colorScheme.surfaceContainerHighest
                      : _stage == _AlexaStage.escuchando
                          ? Theme.of(context).colorScheme.error
                          : Theme.of(context).colorScheme.primary,
                  child: _stage == _AlexaStage.preparando
                      ? const SizedBox(
                          width: 32,
                          height: 32,
                          child: CircularProgressIndicator(strokeWidth: 3),
                        )
                      : Icon(
                          _stage == _AlexaStage.escuchando ? Icons.mic : Icons.mic_none,
                          size: 56,
                          color: Colors.white,
                        ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Text(_stageLabel, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 24),
            if (_lastResponse.isNotEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(_lastResponse, textAlign: TextAlign.center),
                ),
              ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}
