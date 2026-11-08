// lib/screens/diagram_screen.dart
//
// Lienzo móvil SIMPLIFICADO: a diferencia de la versión web, acá no hay
// paneo infinito ni cursores en vivo de otros colaboradores (eso quedó
// para la versión web, que es donde vale la pena en pantalla grande). Lo
// que sí se mantiene es la colaboración real: los cambios de otros
// colaboradores llegan por el mismo WebSocket y actualizan la lista.
//
// Las clases se muestran como tarjetas en una lista (no en un canvas de
// posición libre): más simple de tocar y de editar en un teléfono chico,
// y de todos modos la posición x/y solo importa para el layout visual del
// canvas web.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../models/diagram.dart';
import '../services/realtime_service.dart';
import 'assistant_screen.dart';

class DiagramScreen extends StatefulWidget {
  final String diagramId;
  final String title;
  const DiagramScreen({super.key, required this.diagramId, required this.title});

  @override
  State<DiagramScreen> createState() => _DiagramScreenState();
}

class _DiagramScreenState extends State<DiagramScreen> {
  List<UmlClass> _classes = [];
  List<UmlRelation> _relations = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
    _connectRealtime();
  }

  void _connectRealtime() {
    final app = context.read<AppState>();
    // El RealtimeService vive acá (no en AppState) porque solo tiene sentido
    // mientras esta pantalla está abierta -- igual que useLiveCursors en la
    // versión web se desconecta al salir del diagrama.
    _realtime.connect(widget.diagramId, app.auth.token!);
    _offClassCreated = _realtime.on('class.created', (_) => _load());
    _offClassUpdated = _realtime.on('class.updated', (_) => _load());
    _offClassDeleted = _realtime.on('class.deleted', (_) => _load());
    _offRelationChanged = _realtime.on('relation.created', (_) => _load());
    _offRelationDeleted = _realtime.on('relation.deleted', (_) => _load());
  }

  final _realtime = RealtimeService();
  void Function()? _offClassCreated;
  void Function()? _offClassUpdated;
  void Function()? _offClassDeleted;
  void Function()? _offRelationChanged;
  void Function()? _offRelationDeleted;

  Future<void> _load() async {
    final app = context.read<AppState>();
    try {
      final classes = await app.api.listClasses(widget.diagramId);
      final relations = await app.api.listRelations(widget.diagramId);
      if (!mounted) return;
      setState(() {
        _classes = classes;
        _relations = relations;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  @override
  void dispose() {
    _offClassCreated?.call();
    _offClassUpdated?.call();
    _offClassDeleted?.call();
    _offRelationChanged?.call();
    _offRelationDeleted?.call();
    _realtime.disconnect();
    super.dispose();
  }

  Future<void> _createClass() async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Nueva clase'),
        content: TextField(controller: controller, autofocus: true, decoration: const InputDecoration(labelText: 'Nombre')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Crear')),
        ],
      ),
    );
    if (name == null || name.isEmpty) return;
    final app = context.read<AppState>();
    await app.api.createClass(widget.diagramId, name);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      floatingActionButton: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          FloatingActionButton(
            heroTag: 'assistant',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => AssistantScreen(diagramId: widget.diagramId, onChanged: _load),
              ),
            ),
            tooltip: 'Asistente IA',
            child: const Icon(Icons.mic),
          ),
          const SizedBox(height: 12),
          FloatingActionButton(
            heroTag: 'add-class',
            onPressed: _createClass,
            child: const Icon(Icons.add),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Error: $_error'))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _classes.length,
                    itemBuilder: (context, i) => _ClassCard(
                      umlClass: _classes[i],
                      relations: _relations.where((r) => r.fromClassId == _classes[i].id || r.toClassId == _classes[i].id).toList(),
                      onChanged: _load,
                      diagramId: widget.diagramId,
                    ),
                  ),
                ),
    );
  }
}

class _ClassCard extends StatelessWidget {
  final UmlClass umlClass;
  final List<UmlRelation> relations;
  final String diagramId;
  final VoidCallback onChanged;

  const _ClassCard({
    required this.umlClass,
    required this.relations,
    required this.diagramId,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(umlClass.name, style: Theme.of(context).textTheme.titleMedium),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    await context.read<AppState>().api.deleteClass(umlClass.id);
                    onChanged();
                  },
                ),
              ],
            ),
            if (umlClass.attributes.isNotEmpty) const Divider(),
            for (final a in umlClass.attributes)
              Text('${a.required ? '• ' : '◦ '}${a.name}: ${a.type}', style: Theme.of(context).textTheme.bodySmall),
            if (umlClass.methods.isNotEmpty) const Divider(),
            for (final m in umlClass.methods)
              Text('${m.name}(): ${m.returnType}', style: Theme.of(context).textTheme.bodySmall),
            if (relations.isNotEmpty) ...[
              const Divider(),
              for (final r in relations)
                Text(
                  '${r.originName} ${_arrow(r.type)} ${r.destinationName}',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(fontStyle: FontStyle.italic),
                ),
            ],
          ],
        ),
      ),
    );
  }

  String _arrow(RelationType t) {
    switch (t) {
      case RelationType.inheritance:
        return '▷—';
      case RelationType.composition:
        return '◆—';
      case RelationType.aggregation:
        return '◇—';
      case RelationType.dependency:
        return '- ->';
      case RelationType.association:
        return '—';
    }
  }
}
