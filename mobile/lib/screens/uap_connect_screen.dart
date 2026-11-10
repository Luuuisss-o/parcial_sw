// lib/screens/uap_connect_screen.dart
//
// Elegir cómo conectarse al backend Spring Boot generado (USB o LAN/WiFi,
// ver lib/uap/uap_config.dart) y descubrir su contrato UAP antes de
// entrar al asistente. Si la conexión falla, se muestra el error tal cual
// -- no se inventa un mensaje genérico que oculte si el problema es de
// red, de que el backend no levantó, o de que ese backend no habla UAP.
//
// Visualmente sigue al login (brand.dart).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../uap/uap_client.dart';
import '../uap/uap_config.dart';
import 'brand.dart';
import 'historial_screen.dart';

class UapConnectScreen extends StatefulWidget {
  const UapConnectScreen({super.key});

  @override
  State<UapConnectScreen> createState() => _UapConnectScreenState();
}

class _UapConnectScreenState extends State<UapConnectScreen> {
  UapConnectionMode _mode = UapConnectionMode.usb;
  bool _connecting = false;
  String? _error;

  Future<void> _connect() async {
    setState(() {
      _connecting = true;
      _error = null;
    });
    final app = context.read<AppState>();
    final client = UapClient(UapEndpoint(_mode));
    try {
      await app.connectToUap(client);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const HistorialScreen()));
    } catch (e) {
      setState(() => _error = 'No pude conectarme: $e');
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: BrandColors.cream,
        body: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const BrandPageHeader(
                title: 'Conectar a un backend generado',
                subtitle: 'Elegí cómo llega el teléfono al backend y operalo con el asistente por voz o texto.',
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      '¿Cómo está conectado el teléfono al backend?',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: BrandColors.ink),
                    ),
                    const SizedBox(height: 14),
                    RadioGroup<UapConnectionMode>(
                      groupValue: _mode,
                      onChanged: (v) => setState(() => _mode = v!),
                      child: Column(
                        children: [
                          _ModeOption(
                            mode: UapConnectionMode.usb,
                            selected: _mode == UapConnectionMode.usb,
                            icon: Icons.usb_rounded,
                            accent: BrandColors.amber,
                            title: 'Por USB (adb reverse)',
                            url: UapConfig.usbBackendUrl,
                            onTap: () => setState(() => _mode = UapConnectionMode.usb),
                          ),
                          const SizedBox(height: 12),
                          _ModeOption(
                            mode: UapConnectionMode.deployed,
                            selected: _mode == UapConnectionMode.deployed,
                            icon: Icons.wifi_rounded,
                            accent: BrandColors.mint,
                            title: 'Por WiFi / LAN',
                            url: UapConfig.deployedBackendUrl,
                            onTap: () => setState(() => _mode = UapConnectionMode.deployed),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    if (_error != null) ...[
                      BrandErrorBox(_error!),
                      const SizedBox(height: 16),
                    ],
                    FilledButton.icon(
                      style: brandPrimaryButton(),
                      onPressed: _connecting ? null : _connect,
                      icon: _connecting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: BrandColors.amberInk),
                            )
                          : const Icon(Icons.link_rounded),
                      label: Text(_connecting ? 'Conectando...' : 'Conectar'),
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

/// Opción de conexión: tarjeta blanca seleccionable con el radio a la
/// derecha; la elegida se marca con borde y fondo del color de acento.
class _ModeOption extends StatelessWidget {
  const _ModeOption({
    required this.mode,
    required this.selected,
    required this.icon,
    required this.accent,
    required this.title,
    required this.url,
    required this.onTap,
  });

  final UapConnectionMode mode;
  final bool selected;
  final IconData icon;
  final Color accent;
  final String title;
  final String url;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: brandCardDecoration().copyWith(
        border: Border.all(color: selected ? BrandColors.teal : Colors.transparent, width: 2),
      ),
      clipBehavior: Clip.antiAlias,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: accent.withValues(alpha: 0.15),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 14, 6, 14),
            child: Row(
              children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    color: BrandColors.brand,
                    borderRadius: BorderRadius.circular(13),
                    boxShadow: [BoxShadow(color: accent, offset: const Offset(3, 3))],
                  ),
                  child: Icon(icon, color: accent, size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.w800, color: BrandColors.ink),
                      ),
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: BrandColors.cream,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: BrandColors.line),
                        ),
                        child: Text(
                          url,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12, fontFamily: 'monospace', color: BrandColors.muted),
                        ),
                      ),
                    ],
                  ),
                ),
                Radio<UapConnectionMode>(
                  value: mode,
                  fillColor: WidgetStateProperty.resolveWith(
                    (s) => s.contains(WidgetState.selected) ? BrandColors.teal : BrandColors.muted,
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
