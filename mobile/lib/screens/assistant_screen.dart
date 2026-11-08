// lib/screens/assistant_screen.dart
//
// Pantalla del asistente: STT (Vosk) + LLM local (Qwen2.5 vía llamadart),
// 100% offline. Flujo: el usuario habla o escribe -> se arma un snapshot
// del diagrama actual -> el modelo local decide una tool call -> se aplica
// con ApiClient (que a su vez notifica a otros colaboradores por el mismo
// WebSocket que usa la versión web).

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../models/diagram.dart';
import '../services/local_llm_service.dart';

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
      final llmDone = await app.downloader.isLlmDownloaded();
      final voskDone = await app.downloader.isVoskDownloaded();

      if (!llmDone) {
        setState(() {
          _stage = _Stage.downloading;
          _downloadLabel = 'Preparando modelo de lenguaje (una sola vez)...';
        });
        await app.downloader.ensureLlmModel(onProgress: (p) => setState(() => _downloadProgress = p));
      }
      if (!voskDone) {
        setState(() {
          _stage = _Stage.downloading;
          _downloadLabel = 'Descargando modelo de voz en español (~50 MB, una sola vez)...';
          _downloadProgress = 0;
        });
        await app.downloader.downloadVosk(onProgress: (p) => setState(() => _downloadProgress = p));
      }

      setState(() => _stage = _Stage.loadingEngine);
      final llmPath = await app.downloader.llmModelPath();
      final voskPath = await app.downloader.voskModelPath();
      await app.llm.load(llmPath);
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
      final classes = await app.api.listClasses(widget.diagramId);
      final snapshot = {
        'classes': classes
            .map((c) => {
                  'name': c.name,
                  'attributes': c.attributes.map((a) => {'name': a.name, 'type': a.type, 'required': a.required}).toList(),
                  'methods': c.methods.map((m) => {'name': m.name, 'return_type': m.returnType}).toList(),
                })
            .toList(),
      };

      final call = await app.llm.resolveCommand(userText: text, diagramSnapshot: snapshot);
      final resultText = await _applyToolCall(app, classes, call);

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

  Future<String> _applyToolCall(AppState app, List<UmlClass> classes, LlmToolCall call) async {
    UmlClass? findClass(String? name) {
      if (name == null) return null;
      for (final c in classes) {
        if (c.name.toLowerCase() == name.toLowerCase()) return c;
      }
      return null;
    }

    switch (call.tool) {
      case 'clarify':
        return call.arguments['message'] as String? ?? '¿Podés ser más específico?';

      case 'create_class':
        final name = call.arguments['name'] as String;
        await app.api.createClass(widget.diagramId, name);
        return 'Creé la clase "$name".';

      case 'rename_class':
        final cls = findClass(call.arguments['class_name'] as String?);
        if (cls == null) return 'No encontré esa clase.';
        final newName = call.arguments['new_name'] as String;
        await app.api.updateClass(cls.id, {'name': newName});
        return 'Renombré "${cls.name}" a "$newName".';

      case 'delete_class':
        final cls = findClass(call.arguments['class_name'] as String?);
        if (cls == null) return 'No encontré esa clase.';
        await app.api.deleteClass(cls.id);
        return 'Eliminé la clase "${cls.name}".';

      case 'add_attribute':
        final cls = findClass(call.arguments['class_name'] as String?);
        if (cls == null) return 'No encontré esa clase.';
        final name = call.arguments['name'] as String;
        final type = call.arguments['type'] as String? ?? 'String';
        final required = call.arguments['required'] as bool? ?? false;
        await app.api.createAttribute(cls.id, name, type, required: required);
        return 'Agregué el atributo "$name: $type" a "${cls.name}".';

      case 'delete_attribute':
        final cls = findClass(call.arguments['class_name'] as String?);
        if (cls == null) return 'No encontré esa clase.';
        final attrName = (call.arguments['attribute_name'] as String).toLowerCase();
        final attr = cls.attributes.where((a) => a.name.toLowerCase() == attrName).firstOrNull;
        if (attr == null) return 'No encontré ese atributo en "${cls.name}".';
        await app.api.deleteAttribute(attr.id);
        return 'Eliminé el atributo "${attr.name}" de "${cls.name}".';

      case 'add_method':
        final cls = findClass(call.arguments['class_name'] as String?);
        if (cls == null) return 'No encontré esa clase.';
        final name = call.arguments['name'] as String;
        final returnType = call.arguments['return_type'] as String? ?? 'void';
        await app.api.createMethod(cls.id, name, returnType: returnType);
        return 'Agregué el método "$name()" a "${cls.name}".';

      case 'delete_method':
        final cls = findClass(call.arguments['class_name'] as String?);
        if (cls == null) return 'No encontré esa clase.';
        final methodName = (call.arguments['method_name'] as String).toLowerCase();
        final method = cls.methods.where((m) => m.name.toLowerCase() == methodName).firstOrNull;
        if (method == null) return 'No encontré ese método en "${cls.name}".';
        await app.api.deleteMethod(method.id);
        return 'Eliminé el método "${method.name}" de "${cls.name}".';

      case 'create_relation':
        final from = findClass(call.arguments['from_class'] as String?);
        final to = findClass(call.arguments['to_class'] as String?);
        if (from == null || to == null) return 'No encontré alguna de las dos clases.';
        final type = relationTypeFromString(call.arguments['type'] as String? ?? 'ASSOCIATION');
        await app.api.createRelation(
          diagramId: widget.diagramId,
          fromClass: from.id,
          toClass: to.id,
          type: type,
        );
        return 'Creé la relación entre "${from.name}" y "${to.name}".';

      case 'delete_relation':
        final from = findClass(call.arguments['from_class'] as String?);
        final to = findClass(call.arguments['to_class'] as String?);
        if (from == null || to == null) return 'No encontré alguna de las dos clases.';
        final relations = await app.api.listRelations(widget.diagramId);
        final rel = relations
            .where((r) => (r.fromClassId == from.id && r.toClassId == to.id) || (r.fromClassId == to.id && r.toClassId == from.id))
            .firstOrNull;
        if (rel == null) return 'No encontré esa relación.';
        await app.api.deleteRelation(rel.id);
        return 'Eliminé la relación entre "${from.name}" y "${to.name}".';

      default:
        return 'No reconozco esa acción ("${call.tool}").';
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
