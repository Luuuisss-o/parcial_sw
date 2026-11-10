// lib/app_state.dart
//
// Estado global mínimo compartido entre pantallas: sesión del usuario y los
// servicios que se instancian una sola vez (API, IA local, voz). No guarda
// el diagrama actual completo -- eso vive en la pantalla del diagrama, que
// lo recarga vía ApiClient/RealtimeService.

import 'package:flutter/material.dart';
import 'screens/login_screen.dart';
import 'services/auth_service.dart';
import 'services/api_client.dart';
import 'services/local_llm_service.dart';
import 'services/speech_service.dart';
import 'services/model_downloader.dart';
import 'db/local_repository.dart';
import 'db/uap_database.dart';
import 'uap/connection_manager.dart';
import 'uap/uap_client.dart';
import 'uap/uap_manifest.dart';
import 'voice/tts_service.dart';

/// Navegador raíz: permite volver al login desde cualquier pantalla abierta
/// cuando la sesión vence.
final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();

class AppState extends ChangeNotifier {
  final AuthService auth = AuthService();
  late final ApiClient api = ApiClient(auth)..onUnauthorized = _sessionExpired;
  final LocalLlmService llm = LocalLlmService();
  final SpeechRecognitionService speech = SpeechRecognitionService();
  final ModelDownloader downloader = ModelDownloader();
  final TtsService tts = TtsService();

  bool _ready = false;
  bool get ready => _ready;

  Future<void> bootstrap() async {
    await auth.loadFromDisk();
    await tts.init();
    _ready = true;
    notifyListeners();
  }

  bool get isLoggedIn => auth.token != null;

  Future<void> logout() async {
    await auth.signOut();
    notifyListeners();
  }

  /// El backend rechazó el token (venció a las 8 h o es inválido): se cierra
  /// la sesión y se vuelve al login, que explica el motivo.
  bool _expiring = false;
  Future<void> _sessionExpired() async {
    if (_expiring || auth.token == null) return;
    _expiring = true;
    try {
      await auth.signOut();
      auth.sessionExpired = true;
      notifyListeners();
      rootNavigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (route) => false,
      );
    } finally {
      _expiring = false;
    }
  }

  // ---------------------------------------------------------------
  // Conexión a un backend UAP generado (ver UapConnectScreen, la pantalla
  // de arranque de la app). Se instancian recién al conectar -- no en el
  // constructor -- porque dependen del endpoint (USB/desplegado) que el
  // usuario elija en esa pantalla.
  // ---------------------------------------------------------------
  UapClient? uapClient;
  LocalRepository? localDb;
  ConnectionManager? connection;
  UapContract? contract;

  Future<void> connectToUap(UapClient client) async {
    uapClient = client;
    contract = await client.discover();
    localDb ??= LocalRepository(UapDatabase());
    connection?.dispose();
    connection = ConnectionManager(
      client: client,
      repo: localDb!,
      entityKeys: contract!.manifest.entities.map((e) => e.key).toList(),
    )..start();
    notifyListeners();
  }

  void disconnectFromUap() {
    connection?.dispose();
    uapClient?.close();
    uapClient = null;
    connection = null;
    contract = null;
    notifyListeners();
  }
}
