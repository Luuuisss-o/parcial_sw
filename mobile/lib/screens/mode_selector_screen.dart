// lib/screens/mode_selector_screen.dart
//
// Nueva pantalla de entrada tras el login: elegir entre el flujo del
// diagramador de siempre (editar diagramas UML, sin cambios) o conectarse
// a un backend Spring Boot generado ese día y usar el asistente genérico
// (protocolo UAP). Un solo cambio en main.dart apunta acá en vez de ir
// directo a DiagramListScreen -- el resto del flujo del diagramador queda
// intacto.
//
// Visualmente sigue al login: encabezado verde petróleo con cuadrícula y
// tarjetas blancas con franja de color (paleta de brand.dart).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'brand.dart';
import 'diagram_list_screen.dart';
import 'photo_import_screen.dart';
import 'uap_connect_screen.dart';

class ModeSelectorScreen extends StatefulWidget {
  const ModeSelectorScreen({super.key});

  @override
  State<ModeSelectorScreen> createState() => _ModeSelectorScreenState();
}

class _ModeSelectorScreenState extends State<ModeSelectorScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _recoverLostPhoto());
  }

  /// Importar desde foto: mientras la cámara o la galería están abiertas,
  /// Android puede cerrar la app por falta de memoria (pasó en el celular de
  /// prueba: lmkd "low watermark is breached"). Al volver, la app arranca de
  /// cero en esta pantalla y la foto se perdía. image_picker la guarda: si
  /// hay una pendiente, se retoma el import (Mis diagramas -> revisión).
  Future<void> _recoverLostPhoto() async {
    LostDataResponse lost;
    try {
      lost = await ImagePicker().retrieveLostData();
    } catch (_) {
      return; // plataforma sin soporte (solo aplica en Android)
    }
    final file = lost.file;
    if (lost.isEmpty || file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    final nav = Navigator.of(context);
    nav.push(MaterialPageRoute(builder: (_) => const DiagramListScreen()));
    nav.push(MaterialPageRoute(builder: (_) => PhotoImportScreen(bytes: bytes, filename: file.name)));
  }

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.of(context).padding.top;
    // Encabezado oscuro: íconos de la barra de estado en claro.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: BrandColors.cream,
        body: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              CustomPaint(
                painter: const BrandGridPainter(),
                child: Padding(
                  padding: EdgeInsets.fromLTRB(22, top + 22, 22, 28),
                  child: const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          BrandLogo(size: 36),
                          SizedBox(width: 12),
                          Text(
                            'UML Collab',
                            style: TextStyle(
                              color: BrandColors.brandText,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 22),
                      Text(
                        '¿Qué querés hacer?',
                        style: TextStyle(
                          color: BrandColors.brandText,
                          fontSize: 26,
                          height: 1.15,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.4,
                        ),
                      ),
                      SizedBox(height: 8),
                      Text(
                        'Elegí cómo querés trabajar hoy.',
                        style: TextStyle(color: BrandColors.brandMuted, fontSize: 14),
                      ),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _ModeCard(
                          icon: Icons.schema_outlined,
                          accent: BrandColors.amber,
                          title: 'Diseñar diagramas',
                          subtitle: 'Editar diagramas de clases UML, como siempre.',
                          tags: const ['Tiempo real', 'Asesor de IA'],
                          onTap: () =>
                              Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DiagramListScreen())),
                        ),
                        const SizedBox(height: 16),
                        _ModeCard(
                          icon: Icons.smart_toy_outlined,
                          accent: BrandColors.mint,
                          title: 'Usar un sistema generado',
                          subtitle: 'Conectarse a un backend generado hoy y operarlo con el asistente por voz o texto.',
                          tags: const ['USB o WiFi', 'Voz'],
                          onTap: () =>
                              Navigator.of(context).push(MaterialPageRoute(builder: (_) => const UapConnectScreen())),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  final IconData icon;
  final Color accent;
  final String title;
  final String subtitle;
  final List<String> tags;
  final VoidCallback onTap;

  const _ModeCard({
    required this.icon,
    required this.accent,
    required this.title,
    required this.subtitle,
    required this.tags,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [
          BoxShadow(color: Color(0x1F0E3B36), blurRadius: 24, offset: Offset(0, 10)),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: accent.withValues(alpha: 0.15),
          highlightColor: accent.withValues(alpha: 0.08),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(height: 4, color: accent),
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 18, 14, 18),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: BrandColors.brand,
                        borderRadius: BorderRadius.circular(13),
                        boxShadow: [BoxShadow(color: accent, offset: const Offset(3, 3))],
                      ),
                      child: Icon(icon, color: accent, size: 26),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w800,
                              color: BrandColors.ink,
                              letterSpacing: -0.2,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            subtitle,
                            style: const TextStyle(fontSize: 14, height: 1.35, color: BrandColors.muted),
                          ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 6,
                            runSpacing: 6,
                            children: [
                              for (final t in tags)
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: BrandColors.cream,
                                    borderRadius: BorderRadius.circular(999),
                                    border: Border.all(color: BrandColors.line),
                                  ),
                                  child: Text(
                                    t,
                                    style: const TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: BrandColors.ink,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: BrandColors.cream,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.arrow_forward_rounded, size: 18, color: BrandColors.ink),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
