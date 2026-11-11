// lib/screens/photo_import_screen.dart
//
// Importar un diagrama desde una foto, igual que la web
// (frontend/src/components/panels/ImportFromPhotoModal.jsx): la IA lee la
// imagen -- diagrama de clases UML o de base de datos (tablas con PK/FK,
// pata de gallo, Chen) -- y ANTES de crear nada se muestra lo leído para que
// el usuario destilde lo que no corresponda. Recién al confirmar se crea el
// diagrama nuevo y se abre.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import 'brand.dart';
import 'diagram_screen.dart';

class PhotoImportScreen extends StatefulWidget {
  const PhotoImportScreen({super.key, required this.bytes, required this.filename});

  final Uint8List bytes;
  final String filename;

  @override
  State<PhotoImportScreen> createState() => _PhotoImportScreenState();
}

class _PhotoImportScreenState extends State<PhotoImportScreen> {
  bool _reading = true;
  bool _creating = false;
  String? _error;
  String _source = 'uml';
  final _titleCtrl = TextEditingController(text: 'Diagrama importado');

  // Lo leído, con un "seleccionado" por elemento.
  List<Map<String, dynamic>> _classes = [];
  List<Map<String, dynamic>> _relations = [];

  @override
  void initState() {
    super.initState();
    _detect();
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    super.dispose();
  }

  Future<void> _detect() async {
    setState(() {
      _reading = true;
      _error = null;
    });
    try {
      final r = await context.read<AppState>().api.detectDiagramFromImage(widget.bytes, widget.filename);
      if (!mounted) return;
      setState(() {
        _source = (r['source'] ?? 'uml') as String;
        _classes = ((r['classes'] ?? []) as List).map((c) {
          final m = Map<String, dynamic>.from(c as Map);
          m['selected'] = true;
          m['attributes'] = ((m['attributes'] ?? []) as List)
              .map((a) => {...Map<String, dynamic>.from(a as Map), 'selected': true})
              .toList();
          m['methods'] = ((m['methods'] ?? []) as List)
              .map((x) => {...Map<String, dynamic>.from(x as Map), 'selected': true})
              .toList();
          return m;
        }).toList();
        _relations = ((r['relations'] ?? []) as List)
            .map((x) => {...Map<String, dynamic>.from(x as Map), 'selected': true})
            .toList();
        _error = r['warning'] as String?;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _reading = false);
    }
  }

  Set<String> get _selectedNames =>
      _classes.where((c) => c['selected'] == true).map((c) => c['name'] as String).toSet();

  Future<void> _create() async {
    setState(() {
      _creating = true;
      _error = null;
    });
    final names = _selectedNames;
    List<Map<String, dynamic>> picked(List list) => list
        .where((x) => x['selected'] == true)
        .map((x) => Map<String, dynamic>.from(x as Map)..remove('selected'))
        .toList();
    final body = {
      'title': _titleCtrl.text.trim().isEmpty ? 'Diagrama importado' : _titleCtrl.text.trim(),
      'classes': _classes
          .where((c) => c['selected'] == true)
          .map((c) => {
                'name': c['name'],
                'kind': c['kind'] ?? 'class',
                'attributes': picked(c['attributes'] as List),
                'methods': picked(c['methods'] as List),
              })
          .toList(),
      'relations':
          picked(_relations).where((r) => names.contains(r['from_class']) && names.contains(r['to_class'])).toList(),
    };
    try {
      final summary = await context.read<AppState>().api.applyDetectedDiagram(body);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => DiagramScreen(diagramId: summary['diagram_id'] as String, title: body['title'] as String),
      ));
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '$e';
          _creating = false;
        });
      }
    }
  }

  static String _fmtAttr(Map a) =>
      '${a['visibility'] ?? '-'} ${a['is_derived'] == true ? '/' : ''}${a['name']} : ${a['type'] ?? 'string'}'
      '${(a['multiplicity'] ?? '') != '' ? ' [${a['multiplicity']}]' : ''}'
      '${(a['default_value'] ?? '') != '' ? ' = ${a['default_value']}' : ''}'
      '${a['required'] == true ? ' *' : ''}';

  static String _fmtMeth(Map m) =>
      '${m['visibility'] ?? '+'} ${m['name']}(${m['params'] ?? ''}) : ${m['return_type'] ?? 'void'}';

  static const _relLabel = {
    'ASSOCIATION': 'asociación',
    'AGGREGATION': 'agregación',
    'COMPOSITION': 'composición',
    'INHERITANCE': 'herencia',
    'REALIZATION': 'realización',
    'DEPENDENCY': 'dependencia',
  };

  @override
  Widget build(BuildContext context) {
    final nSel = _selectedNames.length;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: BrandColors.cream,
        bottomNavigationBar: _reading || _classes.isEmpty
            ? null
            : SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
                  child: FilledButton.icon(
                    style: brandPrimaryButton(),
                    onPressed: _creating || nSel == 0 ? null : _create,
                    icon: _creating
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: BrandColors.amberInk),
                          )
                        : const Icon(Icons.check_rounded),
                    label: Text(_creating ? 'Creando…' : 'Crear diagrama ($nSel clase${nSel == 1 ? '' : 's'})'),
                  ),
                ),
              ),
        body: ListView(
          padding: EdgeInsets.zero,
          children: [
            const BrandPageHeader(
              title: 'Importar desde foto',
              subtitle: 'La IA lee el diagrama (de clases o de base de datos). Revisalo antes de crearlo.',
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(14),
                    child: Image.memory(widget.bytes, height: 180, fit: BoxFit.cover),
                  ),
                  const SizedBox(height: 16),
                  if (_reading) ...[
                    const Center(child: CircularProgressIndicator(color: BrandColors.teal)),
                    const SizedBox(height: 12),
                    const Text(
                      'Leyendo la imagen… puede tardar unos segundos.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: BrandColors.muted),
                    ),
                  ],
                  if (_error != null) ...[
                    BrandErrorBox(_error!),
                    const SizedBox(height: 12),
                  ],
                  if (!_reading && _classes.isEmpty)
                    OutlinedButton.icon(
                      onPressed: () => Navigator.of(context).pop(),
                      icon: const Icon(Icons.photo_camera_outlined),
                      label: const Text('Probar con otra foto'),
                    ),
                  if (!_reading && _classes.isNotEmpty) ..._review(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _review() => [
        if (_source == 'er')
          Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: BrandColors.mint.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Text(
              'Se detectó un diagrama de base de datos: cada tabla pasa a ser una clase y cada '
              'clave foránea, una relación con su multiplicidad.',
              style: TextStyle(color: BrandColors.ink, fontSize: 13),
            ),
          ),
        TextField(
          controller: _titleCtrl,
          decoration: InputDecoration(
            labelText: 'Título del diagrama nuevo',
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 16),
        for (final c in _classes) _classCard(c),
        if (_relations.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Text('Relaciones', style: TextStyle(fontWeight: FontWeight.w800, color: BrandColors.ink)),
          const SizedBox(height: 6),
          for (final r in _relations) _relationTile(r),
        ],
      ];

  Widget _classCard(Map<String, dynamic> c) {
    final sel = c['selected'] == true;
    final kind = c['kind'] as String? ?? 'class';
    final isEnum = kind == 'enumeration';
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: brandCardDecoration(),
      child: Opacity(
        opacity: sel ? 1 : 0.5,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 4, 12, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CheckboxListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                activeColor: BrandColors.teal,
                value: sel,
                onChanged: (v) => setState(() => c['selected'] = v ?? false),
                title: Text(
                  c['name'] as String,
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: BrandColors.ink,
                    fontStyle: kind == 'abstract' || kind == 'interface' ? FontStyle.italic : FontStyle.normal,
                  ),
                ),
                subtitle: switch (kind) {
                  'interface' => const Text('«interface»'),
                  'enumeration' => const Text('«enumeration»'),
                  'abstract' => const Text('abstracta'),
                  _ => null,
                },
              ),
              for (final a in c['attributes'] as List)
                _memberRow(a as Map<String, dynamic>, isEnum ? a['name'] as String : _fmtAttr(a), sel,
                    underline: a['is_static'] == true),
              for (final m in c['methods'] as List)
                _memberRow(m as Map<String, dynamic>, _fmtMeth(m), sel,
                    underline: m['is_static'] == true, italic: m['is_abstract'] == true),
            ],
          ),
        ),
      ),
    );
  }

  Widget _memberRow(Map<String, dynamic> x, String text, bool enabled, {bool underline = false, bool italic = false}) {
    return InkWell(
      onTap: enabled ? () => setState(() => x['selected'] = !(x['selected'] == true)) : null,
      child: Padding(
        padding: const EdgeInsets.only(left: 40, top: 2, bottom: 2),
        child: Row(
          children: [
            Icon(
              x['selected'] == true ? Icons.check_box_rounded : Icons.check_box_outline_blank_rounded,
              size: 18,
              color: BrandColors.teal,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                text,
                style: TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12.5,
                  color: BrandColors.muted,
                  decoration: underline ? TextDecoration.underline : TextDecoration.none,
                  fontStyle: italic ? FontStyle.italic : FontStyle.normal,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _relationTile(Map<String, dynamic> r) {
    final ok = _selectedNames.contains(r['from_class']) && _selectedNames.contains(r['to_class']);
    final src = (r['src_multiplicity'] ?? '') != '' ? ' [${r['src_multiplicity']}]' : '';
    final dst = (r['dst_multiplicity'] ?? '') != '' ? ' [${r['dst_multiplicity']}]' : '';
    return CheckboxListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      controlAffinity: ListTileControlAffinity.leading,
      activeColor: BrandColors.teal,
      value: ok && r['selected'] == true,
      onChanged: ok ? (v) => setState(() => r['selected'] = v ?? false) : null,
      title: Text(
        '${r['from_class']}$src → ${r['to_class']}$dst',
        style: const TextStyle(color: BrandColors.ink, fontSize: 13.5),
      ),
      subtitle: Text(ok ? (_relLabel[r['type']] ?? '${r['type']}') : 'Se excluye una de las clases'),
    );
  }
}
