// lib/screens/mode_selector_screen.dart
//
// Nueva pantalla de entrada tras el login: elegir entre el flujo del
// diagramador de siempre (editar diagramas UML, sin cambios) o conectarse
// a un backend Spring Boot generado ese día y usar el asistente genérico
// (protocolo UAP). Un solo cambio en main.dart apunta acá en vez de ir
// directo a DiagramListScreen -- el resto del flujo del diagramador queda
// intacto.

import 'package:flutter/material.dart';
import 'diagram_list_screen.dart';
import 'uap_connect_screen.dart';

class ModeSelectorScreen extends StatelessWidget {
  const ModeSelectorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('¿Qué querés hacer?')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _ModeCard(
              icon: Icons.schema_outlined,
              title: 'Diseñar diagramas',
              subtitle: 'Editar diagramas de clases UML, como siempre.',
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DiagramListScreen())),
            ),
            const SizedBox(height: 16),
            _ModeCard(
              icon: Icons.smart_toy_outlined,
              title: 'Usar un sistema generado',
              subtitle: 'Conectarse a un backend generado hoy y operarlo con el asistente por voz o texto.',
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const UapConnectScreen())),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _ModeCard({required this.icon, required this.title, required this.subtitle, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: Icon(icon, size: 32),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(subtitle),
        onTap: onTap,
      ),
    );
  }
}
