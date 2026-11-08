// lib/screens/team_chat_screen.dart
//
// Chat del equipo en el celular (Fase 2): mismo canal que la versión web.
// Todos los integrantes ven los mensajes y las consultas a la IA.
//
// La novedad del móvil: las consultas "@IA" que hace ESTE usuario pueden
// responderse con el modelo PERSONALIZADO que corre localmente en el
// teléfono (llama.cpp). El servidor solo aloja el archivo del modelo; la
// inferencia es local. La respuesta se publica en el chat, dirigida a quien
// preguntó y visible para todo el equipo, igual que una del servidor.
// Con el interruptor "IA en este celular" apagado, responde la IA del
// servidor (Gemini o el proveedor que haya configurado el dueño).

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../models/chat.dart';
import '../services/diagram_tool_runner.dart';
import '../services/local_team_assistant.dart';
import '../services/realtime_service.dart';

class TeamChatScreen extends StatefulWidget {
  final String diagramId;
  final String title;
  final RealtimeService realtime;
  const TeamChatScreen({super.key, required this.diagramId, required this.title, required this.realtime});

  @override
  State<TeamChatScreen> createState() => _TeamChatScreenState();
}

enum _ModelState { unknown, preparing, ready, unavailable }

class _TeamChatScreenState extends State<TeamChatScreen> {
  final _messages = <String, ChatMessage>{};
  final _pending = <String, String>{}; // request_id -> nombre de quien preguntó
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _offs = <void Function()>[];

  bool _loading = true;
  bool _sending = false;
  bool _onDevice = true;
  _ModelState _modelState = _ModelState.unknown;
  double _modelProgress = 0;
  String? _modelInfo;
  String? _error;

  AppState get _app => context.read<AppState>();

  @override
  void initState() {
    super.initState();
    _offs.addAll([
      widget.realtime.on('chat.message', (d) {
        final m = ChatMessage.fromJson(d);
        if (m.diagramId == widget.diagramId) _add([m]);
      }),
      widget.realtime.on('ai.started', (d) {
        final id = d['request_id'] as String?;
        if (id == null) return;
        final name = (d['requested_by'] as Map?)?['name'] as String? ?? 'alguien';
        setState(() => _pending[id] = d['on_device'] == true ? '$name (en su celular)' : name);
      }),
      // Si el canal se cayó y volvió, recargar lo que no llegó en el medio
      // (por ejemplo la respuesta de la IA del celular).
      widget.realtime.on('reconnected', (_) => _loadHistory()),
      for (final ev in ['ai.done', 'ai.error'])
        widget.realtime.on(ev, (d) => setState(() => _pending.remove(d['request_id']))),
    ]);
    _loadHistory();
    _prepareModel();
  }

  @override
  void dispose() {
    for (final off in _offs) {
      off();
    }
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _add(List<ChatMessage> items) {
    if (!mounted) return;
    setState(() {
      for (final m in items) {
        _messages[m.id] = m;
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  Future<void> _loadHistory() async {
    try {
      _add(await _app.api.listChat(widget.diagramId, limit: 100));
    } catch (e) {
      _error = 'No se pudo cargar el chat: $e';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Deja listo el modelo local: el personalizado del servidor si hay uno
  /// (se descarga una sola vez y se verifica el SHA-256), si no el modelo
  /// base empaquetado en el APK.
  Future<void> _prepareModel() async {
    final app = _app;
    setState(() => _modelState = _ModelState.preparing);
    try {
      String path;
      final manifest = await app.downloader.syncCustomModel(
        app.api,
        onProgress: (p) => mounted ? setState(() => _modelProgress = p) : null,
      );
      final installed = await app.downloader.installedCustomVersion();
      if (installed != null) {
        path = await app.downloader.customModelPath();
        app.llm.modelLabel = 'Gemma 3 1B personalizado v$installed (móvil)';
        _modelInfo = manifest == null
            ? 'Modelo personalizado v$installed (sin conexión al servidor: se usa el ya descargado)'
            : 'Modelo personalizado v$installed';
      } else {
        await app.downloader.ensureLlmModel(onProgress: (p) => mounted ? setState(() => _modelProgress = p) : null);
        path = await app.downloader.llmModelPath();
        app.llm.modelLabel = 'Gemma 3 1B base (móvil)';
        _modelInfo = 'El servidor no tiene modelo personalizado: se usa el modelo base del APK';
      }
      await app.llm.load(path);
      if (mounted) setState(() => _modelState = _ModelState.ready);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _modelState = _ModelState.unavailable;
        _onDevice = false;
        _modelInfo = 'IA local no disponible ($e). Las consultas las responde el servidor.';
      });
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _sending) return;
    final asksAi = mentionsAi(text);
    // Antes, mientras el modelo cargaba, la consulta se iba al servidor sin
    // avisar y parecía que respondía el celular. Ahora se espera.
    if (asksAi && _onDevice && (_modelState == _ModelState.preparing || _modelState == _ModelState.unknown)) {
      final pct = _modelProgress > 0 && _modelProgress < 1 ? ' (${(_modelProgress * 100).round()} %)' : '';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('La IA del celular todavía se está cargando$pct. Esperá unos segundos y enviá de nuevo.'),
      ));
      return;
    }
    final local = asksAi && _onDevice && _modelState == _ModelState.ready;
    setState(() => _sending = true);
    try {
      final q = await _app.api.sendChat(widget.diagramId, text, askAi: asksAi, answerOnDevice: local);
      _input.clear();
      _add([q]);
      if (local) {
        final app = _app;
        final runner = DiagramToolRunner(app.api, widget.diagramId);
        // No se espera: la respuesta llega a todos (incluido este celular)
        // por WebSocket cuando el modelo termina.
        LocalTeamAssistant(
          fetchContext: (id) => app.api.questionContext(widget.diagramId, id),
          model: app.llm.answerTeamQuestion,
          runActions: runner.runAll,
          postAnswer: (id, {content, error, actions, aiMode, modelLabel}) => app.api.postDeviceAnswer(
            widget.diagramId, id,
            content: content, error: error, actions: actions, aiMode: aiMode, modelLabel: modelLabel),
          modelLabel: () => app.llm.modelLabel,
        ).answer(q.id);
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('No se pudo enviar: $e')));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final me = _app.auth.email;
    final items = _messages.values.toList()..sort((a, b) => a.seq.compareTo(b.seq));
    return Scaffold(
      appBar: AppBar(title: Text('Chat · ${widget.title}')),
      body: Column(
        children: [
          _ModelBanner(
            state: _modelState,
            progress: _modelProgress,
            info: _modelInfo,
            onDevice: _onDevice,
            onToggle: _modelState == _ModelState.ready ? (v) => setState(() => _onDevice = v) : null,
          ),
          if (_error != null) Padding(padding: const EdgeInsets.all(8), child: Text(_error!)),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView(
                    controller: _scroll,
                    padding: const EdgeInsets.all(12),
                    children: [
                      if (items.isEmpty)
                        const Padding(
                          padding: EdgeInsets.all(16),
                          child: Text('Escribí al equipo. Empezá con @IA para consultarle a la IA: '
                              'la pregunta y la respuesta las ven todos.'),
                        ),
                      for (final m in items) _Bubble(m: m, mine: !m.isAi && m.authorEmail == me),
                      for (final name in _pending.values)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          child: Row(children: [
                            const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                            const SizedBox(width: 8),
                            Text('La IA está respondiendo a $name…', style: Theme.of(context).textTheme.bodySmall),
                          ]),
                        ),
                    ],
                  ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 8, 8),
              child: Row(children: [
                Expanded(
                  child: TextField(
                    controller: _input,
                    minLines: 1,
                    maxLines: 4,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(hintText: 'Mensaje, o @IA para la IA', border: OutlineInputBorder()),
                  ),
                ),
                IconButton(
                  onPressed: _sending ? null : _send,
                  icon: _sending
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.send),
                ),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _ModelBanner extends StatelessWidget {
  final _ModelState state;
  final double progress;
  final String? info;
  final bool onDevice;
  final ValueChanged<bool>? onToggle;
  const _ModelBanner({required this.state, required this.progress, required this.info, required this.onDevice, this.onToggle});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 4, 6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.phone_android, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                state == _ModelState.ready
                    ? (onDevice ? 'Tus consultas @IA las responde el modelo de este celular' : 'Tus consultas @IA las responde el servidor')
                    : state == _ModelState.preparing
                        ? 'Preparando la IA local…'
                        : 'IA local no disponible',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            Switch(value: onDevice && state == _ModelState.ready, onChanged: onToggle),
          ]),
          if (state == _ModelState.preparing && progress > 0 && progress < 1) LinearProgressIndicator(value: progress),
          if (info != null) Text(info!, style: Theme.of(context).textTheme.labelSmall),
        ]),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  final ChatMessage m;
  final bool mine;
  const _Bubble({required this.m, required this.mine});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final small = Theme.of(context).textTheme.labelSmall;
    final time = DateFormat.Hm().format(m.createdAt);
    final header = m.isAi
        ? '${m.authorName}${m.aiModelLabel != null ? ' · ${m.aiModelLabel}' : ''} → @${m.addressedToName ?? ''} · $time'
        : '${mine ? 'Vos' : m.authorName} · $time';
    final color = m.role == 'ERROR'
        ? scheme.errorContainer
        : m.isAi
            ? scheme.secondaryContainer
            : mine
                ? scheme.primaryContainer
                : scheme.surfaceContainerHigh;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.85),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 4),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(12)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(header, style: small),
            if (m.asksAi) Text('✨ Pregunta a la IA', style: small),
            if (m.aiMode == 'MENTOR' && m.role == 'ASSISTANT') Text('Mentoría · no modifica el diagrama', style: small),
            const SizedBox(height: 4),
            // Las respuestas de la IA pueden traer **negritas**/`código`: se
            // muestran sin los marcadores para que se lean bien en el celular.
            Text(m.isAi ? m.content.replaceAll('**', '').replaceAll('`', '') : m.content),
            if (m.actionsCount > 0)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('✓ Aplicó ${m.actionsCount} cambio(s) en el diagrama', style: small),
              ),
          ]),
        ),
      ),
    );
  }
}
