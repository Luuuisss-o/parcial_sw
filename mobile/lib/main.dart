// lib/main.dart
//
// La app móvil es un cliente del asistente UAP: se conecta a un backend
// Spring Boot generado por el diagramador (protocolo UAP, ver lib/uap/) y
// lo opera por voz o texto. Diseñar diagramas UML se sigue haciendo desde
// la web (frontend/), no desde el celular -- por eso acá NO hay login del
// diagramador ni selector de modo: se arranca directo en la pantalla de
// conexión UAP.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'app_state.dart';
import 'screens/uap_connect_screen.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(),
      child: const UmlCollabApp(),
    ),
  );
}

class UmlCollabApp extends StatelessWidget {
  const UmlCollabApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Asistente UAP',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF4F7CFF), useMaterial3: true),
      home: const _Bootstrapper(),
    );
  }
}

class _Bootstrapper extends StatefulWidget {
  const _Bootstrapper();

  @override
  State<_Bootstrapper> createState() => _BootstrapperState();
}

class _BootstrapperState extends State<_Bootstrapper> {
  @override
  void initState() {
    super.initState();
    context.read<AppState>().bootstrap();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    if (!app.ready) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return const UapConnectScreen();
  }
}
