// lib/screens/assistant_screen.dart
//
// Pantalla del asistente: STT (Vosk) + LLM local (Qwen2.5 vía llamadart),
// 100% offline. Flujo: el usuario habla o escribe -> se arma un snapshot
// del diagrama actual -> el modelo local decide una tool call -> se aplica
// con ApiClient (que a su vez notifica a otros colaboradores por el mismo
// WebSocket que usa la versión web).

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../services/diagram_tool_runner.dart';
import '../services/local_team_assistant.dart' show destructiveConfirmationNeeded, kMaxActionsPerAnswer;

class AssistantScreen extends StatefulWidget {
  final String diagramId;
  final VoidCallback onChanged;
  const AssistantScreen({super.key, required this.diagramId, required this.onChanged});

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

enum _Stage { checkingModels, downloading, loadingEngine, ready, error }

class _AssistantScreenState extends State<AssistantScreen> {
  _Stage _stage = _Stage.checkingModels;
  double _downloadProgress = 0;
  String? _downloadLabel;
  String? _errorMessage;

  final _textCtrl = TextEditingController();
  bool _listening = false;
  bool _thinking = false;
  String _partialText = '';
  final List<_ChatEntry> _history = [];

  @override
  void initState() {
    super.initState();
    _prepare();
  }

  Future<void> _prepare() async {
    final app = context.read<AppState>();
    try {
      setState(() {
        _stage = _Stage.downloading;
        _downloadLabel = 'Preparando el modelo de IA (la primera vez se descarga, ~0,8 GB)...';
      });
      final model = await app.downloader.prepareAssistantModel(
        app.api,
        onProgress: (p) => mounted ? setState(() => _downloadProgress = p) : null,
      );
      app.llm.modelLabel = model.label;
      if (!await app.downloader.isVoskDownloaded()) {
        setState(() {
          _stage = _Stage.downloading;
          _downloadLabel = 'Descargando modelo de voz en español (~50 MB, una sola vez)...';
          _downloadProgress = 0;
        });
        await app.downloader.downloadVosk(onProgress: (p) => setState(() => _downloadProgress = p));
      }

      setState(() => _stage = _Stage.loadingEngine);
      final voskPath = await app.downloader.voskModelPath();
      await app.llm.load(model.path);
      await app.speech.load(voskPath);

      if (!mounted) return;
      setState(() => _stage = _Stage.ready);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _stage = _Stage.error;
        _errorMessage = '$e';
      });
    }
  }

  Future<void> _toggleListening() async {
    final app = context.read<AppState>();
    if (_listening) {
      await app.speech.stopListening();
      setState(() => _listening = false);
      return;
    }
    setState(() {
      _listening = true;
      _partialText = '';
    });
    await app.speech.startListening(
      onPartial: (text) => setState(() => _partialText = text),
      onFinal: (text) {
        setState(() {
          _listening = false;
          _partialText = '';
        });
        app.speech.stopListening();
        _sendCommand(text);
      },
    );
  }

  Future<void> _sendCommand(String text) async {
    if (text.trim().isEmpty) return;
    final app = context.read<AppState>();
    setState(() {
      _history.add(_ChatEntry(text: text, isUser: true));
      _thinking = true;
    });
    _textCtrl.clear();

    try {
      // Mismo contrato con el que se entrenó el modelo personalizado (el del
      // chat del equipo, assistant_prompt.dart) y mismo ejecutor de
      // acciones: con el prompt viejo de resolveCommand el modelo
      // personalizado contesta en otro formato.
      final classes = await app.api.listClasses(widget.diagramId);
      final relations = await app.api.listRelations(widget.diagramId);
      final me = (app.auth.email ?? 'usuario').split('@').first;
      final ctx = <String, dynamic>{
        'requester_name': me,
        'solutions_enabled': false,
        'question': text,
        'diagram': {
          'clases': [
            for (final c in classes)
              {
                'nombre': c.name,
                'atributos': [for (final a in c.attributes) {'nombre': a.name, 'tipo': a.type}],
                'metodos': [for (final m in c.methods) {'nombre': m.name, 'tipo_retorno': m.returnType}],
              }
          ],
          'relaciones': [
            for (final r in relations)
              {'origen': r.originName, 'destino': r.destinationName, 'tipo': r.type.name.toUpperCase()}
          ],
        },
      };
      final reply = await app.llm.answerTeamQuestion(ctx);
      var actions = reply.actions;
      if (actions.length > kMaxActionsPerAnswer) actions = actions.sublist(0, kMaxActionsPerAnswer);
      final ask = destructiveConfirmationNeeded(actions, ctx['diagram'] as Map<String, dynamic>, text, requester: me);
      if (ask != null) actions = const [];
      final outcomes = actions.isEmpty
          ? const <ActionOutcome>[]
          : await DiagramToolRunner(app.api, widget.diagramId).runAll(actions);
      final failed = outcomes.where((o) => !o.ok).map((o) => '- ${o.message}').toList();
      final done = outcomes.where((o) => o.ok).map((o) => o.message).toList();
      var resultText = ask ?? reply.say.trim();
      if (resultText.isEmpty) resultText = done.isNotEmpty ? done.join(' ') : '¿Podés repetirlo con otras palabras?';
      if (failed.isNotEmpty) resultText += '\n\nNo pude aplicar todo:\n${failed.join('\n')}';

      setState(() {
        _history.add(_ChatEntry(text: resultText, isUser: false));
        _thinking = false;
      });
      widget.onChanged();
    } catch (e) {
      setState(() {
        _history.add(_ChatEntry(text: 'No entendí ese pedido: $e', isUser: false));
        _thinking = false;
      });
    }
  }

  @override
  void dispose() {
    _textCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Asistente IA (offline)')),
      body: switch (_stage) {
        _Stage.checkingModels => const Center(child: CircularProgressIndicator()),
        _Stage.downloading => _DownloadProgressView(label: _downloadLabel ?? '', progress: _downloadProgress),
        _Stage.loadingEngine => const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Cargando el modelo en memoria...'),
                ],
              ),
            ),
          ),
        _Stage.error => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48),
                  const SizedBox(height: 12),
                  Text(_errorMessage ?? 'Error desconocido', textAlign: TextAlign.center),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: _prepare, child: const Text('Reintentar')),
                ],
              ),
            ),
          ),
        _Stage.ready => _buildChat(context),
      },
    );
  }

  Widget _buildChat(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: _history.isEmpty
              ? const Center(child: Text('Decime o escribí qué querés cambiar en el diagrama.'))
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _history.length,
                  itemBuilder: (context, i) {
                    final e = _history[i];
                    return Align(
                      alignment: e.isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: Container(
                        margin: const EdgeInsets.symmetric(vertical: 4),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                        decoration: BoxDecoration(
                          color: e.isUser
                              ? Theme.of(context).colorScheme.primaryContainer
                              : Theme.of(context).colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Text(e.text),
                      ),
                    );
                  },
                ),
        ),
        if (_thinking) const LinearProgressIndicator(),
        if (_listening && _partialText.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(_partialText, style: const TextStyle(fontStyle: FontStyle.italic)),
          ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                IconButton(
                  onPressed: _thinking ? null : _toggleListening,
                  icon: Icon(_listening ? Icons.stop_circle : Icons.mic),
                  color: _listening ? Theme.of(context).colorScheme.error : null,
                ),
                Expanded(
                  child: TextField(
                    controller: _textCtrl,
                    decoration: const InputDecoration(hintText: 'Escribí una instrucción...'),
                    onSubmitted: _thinking ? null : _sendCommand,
                  ),
                ),
                IconButton(
                  onPressed: _thinking ? null : () => _sendCommand(_textCtrl.text),
                  icon: const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _DownloadProgressView extends StatelessWidget {
  final String label;
  final double progress;
  const _DownloadProgressView({required this.label, required this.progress});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            LinearProgressIndicator(value: progress),
            const SizedBox(height: 8),
            Text('${(progress * 100).toStringAsFixed(0)}%'),
          ],
        ),
      ),
    );
  }
}

class _ChatEntry {
  final String text;
  final bool isUser;
  _ChatEntry({required this.text, required this.isUser});
}
