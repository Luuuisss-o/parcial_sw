// Smoke test de UapConnectScreen aislada (no de la app completa): es la
// pantalla real de arranque de la app (ver main.dart) -- el flujo del
// diagramador (login, lista de diagramas) no forma parte del camino
// principal de mobile/, que existe para conectarse a un backend Spring
// Boot generado y operarlo con el asistente, no para diseñar diagramas
// (eso se hace desde la web).
//
// No se testea UmlCollabApp/main.dart de punta a punta acá porque
// AppState() instancia SpeechRecognitionService en su declaración de
// campo, que carga la librería nativa de Vosk (libvosk.dll/.so) al
// construirse -- esa librería no existe en el entorno de test de
// escritorio (ni en CI), así que cualquier widget test que construya un
// AppState real falla por un problema de plataforma, no de lógica. Un
// test de integración real de la app completa solo tiene sentido
// corriendo en un dispositivo/emulador Android de verdad.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:uml_collab_mobile/app_state.dart';
import 'package:uml_collab_mobile/screens/uap_connect_screen.dart';

void main() {
  testWidgets('UapConnectScreen muestra las opciones de conexión USB y WiFi', (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AppState(),
        child: const MaterialApp(home: UapConnectScreen()),
      ),
    );

    expect(find.text('Conectar a un backend generado'), findsOneWidget);
    expect(find.text('Por USB (adb reverse)'), findsOneWidget);
    expect(find.text('Por WiFi / LAN'), findsOneWidget);
    expect(find.text('Conectar'), findsOneWidget);
  });
}
