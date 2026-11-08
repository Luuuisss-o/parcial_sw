// lib/screens/uap_connect_screen.dart
//
// Elegir cómo conectarse al backend Spring Boot generado (USB o LAN/WiFi,
// ver lib/uap/uap_config.dart) y descubrir su contrato UAP antes de
// entrar al asistente. Si la conexión falla, se muestra el error tal cual
// -- no se inventa un mensaje genérico que oculte si el problema es de
// red, de que el backend no levantó, o de que ese backend no habla UAP.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../uap/uap_client.dart';
import '../uap/uap_config.dart';
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
    return Scaffold(
      appBar: AppBar(title: const Text('Conectar a un backend generado')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('¿Cómo está conectado el teléfono al backend?', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            RadioGroup<UapConnectionMode>(
              groupValue: _mode,
              onChanged: (v) => setState(() => _mode = v!),
              child: Column(
                children: [
                  RadioListTile<UapConnectionMode>(
                    title: const Text('Por USB (adb reverse)'),
                    subtitle: Text(UapConfig.usbBackendUrl),
                    value: UapConnectionMode.usb,
                  ),
                  RadioListTile<UapConnectionMode>(
                    title: const Text('Por WiFi / LAN'),
                    subtitle: Text(UapConfig.deployedBackendUrl),
                    value: UapConnectionMode.deployed,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            FilledButton.icon(
              onPressed: _connecting ? null : _connect,
              icon: _connecting
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.link),
              label: Text(_connecting ? 'Conectando...' : 'Conectar'),
            ),
          ],
        ),
      ),
    );
  }
}
