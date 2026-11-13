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
import 'team_chat_screen.dart';
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
  // Colaborador de solo lectura: ve el diagrama y usa el chat, pero no edita.
  bool _readOnly = false;

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
    _offReconnected = _realtime.on('reconnected', (_) => _load());
    // El dueño cambió mi permiso (solo lectura / editor) o me quitó: se
    // recarga el diagrama, y con él mi rol.
    _offCollaborators = _realtime.on('collaborators.changed', (_) => _load());
  }

  final _realtime = RealtimeService();
  void Function()? _offClassCreated;
  void Function()? _offClassUpdated;
  void Function()? _offClassDeleted;
  void Function()? _offRelationChanged;
  void Function()? _offRelationDeleted;
  void Function()? _offReconnected;
  void Function()? _offCollaborators;

  Future<void> _load() async {
    final app = context.read<AppState>();
    try {
      final diagram = await app.api.getDiagram(widget.diagramId);
      final classes = await app.api.listClasses(widget.diagramId);
      final relations = await app.api.listRelations(widget.diagramId);
      if (!mounted) return;
      setState(() {
        _readOnly = diagram.readOnly;
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
    _offReconnected?.call();
    _offCollaborators?.call();
    _realtime.disconnect();
    super.dispose();
  }

  Future<void> _createClass() async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Nueva clase'),
        content:
            TextField(controller: controller, autofocus: true, decoration: const InputDecoration(labelText: 'Nombre')),
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
      appBar: AppBar(
        title: Text(widget.title),
        actions: [
          if (_readOnly)
            const Padding(
              padding: EdgeInsets.only(right: 12),
              child: Chip(avatar: Icon(Icons.visibility_outlined, size: 18), label: Text('Solo lectura')),
            ),
        ],
      ),
      floatingActionButton: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          FloatingActionButton(
            heroTag: 'team-chat',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => TeamChatScreen(diagramId: widget.diagramId, title: widget.title, realtime: _realtime),
              ),
            ),
            tooltip: 'Chat del equipo (IA local en el celular)',
            child: const Icon(Icons.forum),
          ),
          // El asistente por voz y "agregar clase" editan el diagrama.
          if (!_readOnly) ...[
            const SizedBox(height: 12),
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
                      relations: _relations
                          .where((r) => r.fromClassId == _classes[i].id || r.toClassId == _classes[i].id)
                          .toList(),
                      onChanged: _load,
                      diagramId: widget.diagramId,
                      readOnly: _readOnly,
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
  final bool readOnly;

  const _ClassCard({
    required this.umlClass,
    required this.relations,
    required this.diagramId,
    required this.onChanged,
    this.readOnly = false,
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
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // UML 2.5: estereotipo sobre el nombre; abstractas en cursiva.
                      if (_stereotype(umlClass.kind) != null)
                        Text(_stereotype(umlClass.kind)!, style: Theme.of(context).textTheme.labelSmall),
                      Text(
                        umlClass.name,
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontStyle: umlClass.kind == 'abstract' || umlClass.kind == 'interface'
                                  ? FontStyle.italic
                                  : FontStyle.normal,
                            ),
                      ),
                    ],
                  ),
                ),
                if (!readOnly)
                  IconButton(
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () async {
                      // Varios toques seguidos mandaban el mismo DELETE: el
                      // primero borra y los demás daban "Clase no encontrada"
                      // como excepción sin manejar. Ya borrada = objetivo cumplido.
                      try {
                        await context.read<AppState>().api.deleteClass(umlClass.id);
                      } catch (e) {
                        if (!'$e'.contains('no encontrada') && context.mounted) {
                          ScaffoldMessenger.of(context)
                              .showSnackBar(SnackBar(content: Text('No se pudo borrar la clase: $e')));
                        }
                      }
                      onChanged();
                    },
                  ),
              ],
            ),
            if (umlClass.attributes.isNotEmpty) const Divider(),
            // Notación UML 2.5: visibilidad, /derivado, [multiplicidad], = valor;
            // estáticos subrayados, abstractos en cursiva. En una enumeración
            // los atributos son sus literales (solo el nombre).
            for (final a in umlClass.attributes)
              Text(
                umlClass.kind == 'enumeration' ? a.name : '${a.visibility} ${a.umlText}${a.required ? ' *' : ''}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      decoration: a.isStatic ? TextDecoration.underline : TextDecoration.none,
                    ),
              ),
            if (umlClass.methods.isNotEmpty) const Divider(),
            for (final m in umlClass.methods)
              Text(
                '${m.visibility} ${m.umlText}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      decoration: m.isStatic ? TextDecoration.underline : TextDecoration.none,
                      fontStyle: m.isAbstract || umlClass.kind == 'interface' ? FontStyle.italic : FontStyle.normal,
                    ),
              ),
            if (relations.isNotEmpty) ...[
              const Divider(),
              for (final r in relations)
                Text(
                  _relationText(r),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(fontStyle: FontStyle.italic),
                ),
            ],
          ],
        ),
      ),
    );
  }

  static String? _stereotype(String kind) => switch (kind) {
        'interface' => '«interface»',
        'enumeration' => '«enumeration»',
        _ => null,
      };

  /// "Origen [rol] —▷ [rol] Destino". El símbolo va del lado del destino,
  /// como en UML: el triángulo junto al padre / la interfaz, el rombo junto
  /// al todo, la flecha abierta junto al extremo navegable.
  String _relationText(UmlRelation r) {
    final src = r.srcRole != null ? '${r.originName} (${r.srcRole})' : r.originName;
    final dst = r.dstRole != null ? '${r.destinationName} (${r.dstRole})' : r.destinationName;
    return '$src ${_arrow(r)} $dst';
  }

  String _arrow(UmlRelation r) {
    final start = r.srcNavigable ? '<' : '';
    switch (r.type) {
      case RelationType.inheritance:
        return '—▷';
      case RelationType.realization:
        return '- -▷';
      case RelationType.composition:
        return '$start—◆';
      case RelationType.aggregation:
        return '$start—◇';
      case RelationType.dependency:
        return '- ->';
      case RelationType.association:
        return '$start—${r.dstNavigable ? '>' : ''}';
    }
  }
}
