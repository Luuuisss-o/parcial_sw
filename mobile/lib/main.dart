// lib/main.dart
//
// Entrada de la app: sin sesión se muestra el login del diagramador; con
// sesión, el selector de modo (diseñar diagramas -- con el chat del equipo
// y la IA en el celular -- o usar un sistema generado vía protocolo UAP).
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'app_state.dart';
import 'screens/login_screen.dart';
import 'screens/mode_selector_screen.dart';

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
    return app.isLoggedIn ? const ModeSelectorScreen() : const LoginScreen();
  }
}
