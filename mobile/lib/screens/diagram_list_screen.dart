// lib/screens/diagram_list_screen.dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../models/diagram.dart';
import 'diagram_screen.dart';
import 'login_screen.dart';

class DiagramListScreen extends StatefulWidget {
  const DiagramListScreen({super.key});

  @override
  State<DiagramListScreen> createState() => _DiagramListScreenState();
}

class _DiagramListScreenState extends State<DiagramListScreen> {
  late Future<List<Diagram>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Diagram>> _load() => context.read<AppState>().api.listDiagrams();

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  Future<void> _createDiagram() async {
    final controller = TextEditingController();
    final title = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Nuevo diagrama'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Título'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Crear'),
          ),
        ],
      ),
    );
    if (title == null || title.isEmpty) return;
    final app = context.read<AppState>();
    final diagram = await app.api.createDiagram(title);
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => DiagramScreen(diagramId: diagram.id, title: diagram.title)),
    );
    _refresh();
  }

  Future<void> _logout() async {
    await context.read<AppState>().logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mis diagramas'),
        actions: [
          IconButton(onPressed: _logout, icon: const Icon(Icons.logout), tooltip: 'Cerrar sesión'),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _createDiagram,
        child: const Icon(Icons.add),
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<Diagram>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return ListView(
                children: [
                  const SizedBox(height: 80),
                  Center(child: Text('Error: ${snapshot.error}')),
                ],
              );
            }
            final diagrams = snapshot.data ?? [];
            if (diagrams.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 80),
                  Center(child: Text('Todavía no tenés diagramas. Creá uno con el botón +.')),
                ],
              );
            }
            return ListView.separated(
              itemCount: diagrams.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final d = diagrams[i];
                return ListTile(
                  title: Text(d.title),
                  subtitle: Text(d.ownerEmail),
                  trailing: Text(
                    '${d.updatedAt.day}/${d.updatedAt.month}/${d.updatedAt.year}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => DiagramScreen(diagramId: d.id, title: d.title)),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
