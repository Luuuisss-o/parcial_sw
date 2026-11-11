// lib/screens/diagram_list_screen.dart
//
// Lista de diagramas del usuario. Visualmente sigue al login (brand.dart):
// encabezado verde petróleo y tarjetas blancas con franja de color.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../models/diagram.dart';
import 'brand.dart';
import 'package:image_picker/image_picker.dart';
import 'diagram_screen.dart';
import 'login_screen.dart';
import 'photo_import_screen.dart';

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
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        title: const Text(
          'Nuevo diagrama',
          style: TextStyle(fontWeight: FontWeight.w800, color: BrandColors.ink),
        ),
        content: TextField(
          controller: controller,
          autofocus: true,
          cursorColor: BrandColors.teal,
          decoration: InputDecoration(
            labelText: 'Título',
            floatingLabelStyle: const TextStyle(color: BrandColors.teal, fontWeight: FontWeight.w600),
            filled: true,
            fillColor: BrandColors.cream,
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: BrandColors.line),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: BrandColors.teal, width: 2),
            ),
          ),
          onSubmitted: (v) => Navigator.pop(ctx, v.trim()),
        ),
        actions: [
          TextButton(
            style: TextButton.styleFrom(foregroundColor: BrandColors.muted),
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: BrandColors.amber,
              foregroundColor: BrandColors.amberInk,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              textStyle: const TextStyle(fontWeight: FontWeight.w700),
            ),
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Crear'),
          ),
        ],
      ),
    );
    if (title == null || title.isEmpty) return;
    if (!mounted) return;
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

  /// Importar un diagrama desde una foto: cámara o galería (selector del
  /// sistema), y la revisión en PhotoImportScreen antes de crear nada.
  Future<void> _importFromPhoto() async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 4, 20, 8),
                child: Text(
                  'Importar un diagrama de clases o de base de datos',
                  style: TextStyle(fontWeight: FontWeight.w800, color: BrandColors.ink),
                ),
              ),
              ListTile(
                leading: const Icon(Icons.photo_camera_outlined, color: BrandColors.teal),
                title: const Text('Sacar una foto'),
                onTap: () => Navigator.pop(ctx, ImageSource.camera),
              ),
              ListTile(
                leading: const Icon(Icons.photo_library_outlined, color: BrandColors.teal),
                title: const Text('Elegir de la galería'),
                onTap: () => Navigator.pop(ctx, ImageSource.gallery),
              ),
            ],
          ),
        ),
      ),
    );
    if (source == null || !mounted) return;
    // Hasta 10 MB acepta el backend: se achica la foto de la cámara.
    final picked = await ImagePicker().pickImage(source: source, maxWidth: 2400, imageQuality: 85);
    if (picked == null || !mounted) return;
    final bytes = await picked.readAsBytes();
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => PhotoImportScreen(bytes: bytes, filename: picked.name)),
    );
    if (mounted) _refresh();
  }

  void _open(Diagram d) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => DiagramScreen(diagramId: d.id, title: d.title)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final myEmail = context.read<AppState>().auth.email;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: BrandColors.cream,
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _createDiagram,
          backgroundColor: BrandColors.amber,
          foregroundColor: BrandColors.amberInk,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          icon: const Icon(Icons.add_rounded),
          label: const Text('Nuevo diagrama', style: TextStyle(fontWeight: FontWeight.w700)),
        ),
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            FutureBuilder<List<Diagram>>(
              future: _future,
              builder: (context, snapshot) {
                final n = snapshot.data?.length;
                return BrandPageHeader(
                  title: 'Mis diagramas',
                  subtitle: n == null
                      ? 'Tus diagramas y los que compartieron con vos.'
                      : n == 1
                          ? '1 diagrama · deslizá hacia abajo para actualizar.'
                          : '$n diagramas · deslizá hacia abajo para actualizar.',
                  actions: [
                    BrandHeaderButton(
                      icon: Icons.photo_camera_outlined,
                      tooltip: 'Importar desde foto',
                      onPressed: _importFromPhoto,
                    ),
                    const SizedBox(width: 8),
                    BrandHeaderButton(icon: Icons.logout_rounded, tooltip: 'Cerrar sesión', onPressed: _logout),
                  ],
                );
              },
            ),
            Expanded(
              child: RefreshIndicator(
                color: BrandColors.teal,
                onRefresh: _refresh,
                child: FutureBuilder<List<Diagram>>(
                  future: _future,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const Center(child: CircularProgressIndicator(color: BrandColors.teal));
                    }
                    if (snapshot.hasError) {
                      return ListView(
                        padding: const EdgeInsets.all(20),
                        children: [BrandErrorBox('Error: ${snapshot.error}')],
                      );
                    }
                    final diagrams = snapshot.data ?? [];
                    if (diagrams.isEmpty) {
                      return ListView(
                        padding: const EdgeInsets.fromLTRB(32, 64, 32, 32),
                        children: [
                          Center(
                            child: Container(
                              width: 72,
                              height: 72,
                              decoration: BoxDecoration(
                                color: BrandColors.brand,
                                borderRadius: BorderRadius.circular(20),
                                boxShadow: const [BoxShadow(color: BrandColors.amber, offset: Offset(4, 4))],
                              ),
                              child: const Icon(Icons.schema_outlined, color: BrandColors.amber, size: 36),
                            ),
                          ),
                          const SizedBox(height: 20),
                          const Text(
                            'Todavía no tenés diagramas. Creá uno con el botón +.',
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 15, color: BrandColors.muted, height: 1.4),
                          ),
                        ],
                      );
                    }
                    return ListView.separated(
                      padding: const EdgeInsets.fromLTRB(20, 20, 20, 100),
                      itemCount: diagrams.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 12),
                      itemBuilder: (context, i) {
                        final d = diagrams[i];
                        return _DiagramCard(
                          diagram: d,
                          accent: _accents[i % _accents.length],
                          mine: myEmail != null && d.ownerEmail.toLowerCase() == myEmail.toLowerCase(),
                          onTap: () => _open(d),
                        );
                      },
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

const _accents = [BrandColors.amber, BrandColors.mint, BrandColors.coral];

class _DiagramCard extends StatelessWidget {
  const _DiagramCard({required this.diagram, required this.accent, required this.mine, required this.onTap});

  final Diagram diagram;
  final Color accent;
  final bool mine;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final u = diagram.updatedAt;
    final date = '${u.day}/${u.month}/${u.year}';
    return Container(
      decoration: brandCardDecoration(),
      clipBehavior: Clip.antiAlias,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: accent.withValues(alpha: 0.15),
          highlightColor: accent.withValues(alpha: 0.08),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(width: 5, color: accent),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 14, 12, 14),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: BrandColors.brand,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(Icons.account_tree_outlined, color: accent, size: 22),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                diagram.title,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w800,
                                  color: BrandColors.ink,
                                  letterSpacing: -0.2,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Row(
                                children: [
                                  const Icon(Icons.person_outline, size: 14, color: BrandColors.muted),
                                  const SizedBox(width: 4),
                                  Flexible(
                                    child: Text(
                                      diagram.ownerEmail,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(fontSize: 13, color: BrandColors.muted),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children: [
                                  _Tag(mine ? 'Tuyo' : 'Compartido',
                                      icon: mine ? Icons.star_outline_rounded : Icons.group_outlined),
                                  _Tag(date, icon: Icons.schedule_rounded),
                                ],
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: BrandColors.cream,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(Icons.arrow_forward_rounded, size: 18, color: BrandColors.ink),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.label, {required this.icon});
  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: BrandColors.cream,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: BrandColors.line),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: BrandColors.muted),
          const SizedBox(width: 4),
          Text(
            label,
            style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: BrandColors.ink),
          ),
        ],
      ),
    );
  }
}
