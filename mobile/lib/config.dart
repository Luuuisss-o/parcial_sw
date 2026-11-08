// lib/config.dart
//
// Configuración de entorno. El emulador de Android usa 10.0.2.2 para
// llegar al localhost de la PC; un teléfono físico conectado por USB con
// `adb reverse` (ver README de mobile/) usa localhost normal porque el
// puerto queda reenviado. Si probás contra el celular en la misma red
// WiFi que la PC, cambiá esto por la IP local de la PC (ej. 192.168.0.X).

class AppConfig {
  /// Base URL del backend FastAPI (HTTP).
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Base URL del mismo backend pero para WebSocket.
  static String get wsBaseUrl =>
      apiBaseUrl.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://');
}
