// lib/services/realtime_service.dart
//
// Canal WebSocket del diagrama: mismo protocolo que usa el editor web
// (backend/app/routers/realtime.py). Por acá llegan los cambios que hacen
// otros colaboradores (clase creada/editada, atributo agregado, etc.) y el
// estado de exclusión mutua a nivel de clase.
//
// El asistente de IA LOCAL no pasa por este canal para pensar (eso corre
// enteramente en el teléfono, sin red): pero cuando decide crear una clase o
// un atributo, ese cambio se aplica llamando a ApiClient igual que cualquier
// edición manual, y por lo tanto SÍ se notifica por acá a los demás
// colaboradores en tiempo real -- así una edición por voz local se ve al
// instante en la versión web de otra persona, y viceversa.

import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config.dart';

typedef RealtimeListener = void Function(Map<String, dynamic> data);

/// nginx (frontend/nginx.prod.conf.template) corta un WebSocket tras 100 s
/// sin tráfico. La web siempre manda cursores, pero el celular puede pasar
/// minutos callado (descargando el modelo o mientras la IA local piensa):
/// sin esto el canal moría en silencio y dejaban de llegar las respuestas
/// del chat y los cambios del diagrama.
const Duration kWsPingInterval = Duration(seconds: 25);

class RealtimeService {
  WebSocketChannel? _channel;
  String? _diagramId;
  String? _token;
  String? _connId;
  StreamSubscription? _sub;
  Timer? _retry;
  int _attempt = 0;
  bool _reconnecting = false;

  final Map<String, List<RealtimeListener>> _listeners = {};

  String? get connId => _connId;
  bool get isConnected => _channel != null;

  void connect(String diagramId, String token) {
    if (_channel != null && _diagramId == diagramId) return;
    disconnect();
    _diagramId = diagramId;
    _token = token;
    _open();
  }

  void _open() {
    final diagramId = _diagramId, token = _token;
    if (diagramId == null || token == null) return;
    final uri = Uri.parse('${AppConfig.wsBaseUrl}/diagrams/$diagramId/ws?token=${Uri.encodeComponent(token)}');
    _channel = IOWebSocketChannel.connect(uri, pingInterval: kWsPingInterval);

    _sub = _channel!.stream.listen(
      (raw) {
        Map<String, dynamic> msg;
        try {
          msg = jsonDecode(raw as String) as Map<String, dynamic>;
        } catch (_) {
          return;
        }
        final event = msg['event'] as String?;
        // La mayoría de los eventos traen un objeto, pero algunos (ej.
        // "presence", Fase 2) traen una lista: se entrega como {"items": [...]}
        // en vez de romper con un cast inválido.
        final rawData = msg['data'];
        final data = rawData is Map
            ? rawData.cast<String, dynamic>()
            : <String, dynamic>{if (rawData is List) 'items': rawData};
        if (event == 'connected') {
          _connId = data['conn_id'] as String?;
          _attempt = 0;
          // Lo que pasó mientras estuvimos desconectados no llegó: las
          // pantallas escuchan 'reconnected' para recargar.
          if (_reconnecting) {
            _reconnecting = false;
            _emit('reconnected', const {});
          }
          return;
        }
        if (event != null) _emit(event, data);
      },
      onDone: _scheduleReconnect,
      onError: (_) => _scheduleReconnect(),
      cancelOnError: true,
    );
  }

  /// Reintenta con espera creciente (2, 4, 8... hasta 30 s) mientras la
  /// pantalla siga abierta (disconnect() pone _diagramId en null).
  void _scheduleReconnect() {
    _sub?.cancel();
    _channel = null;
    _connId = null;
    if (_diagramId == null || _retry != null) return;
    _reconnecting = true;
    final secs = (2 << _attempt).clamp(2, 30);
    _attempt = (_attempt + 1).clamp(0, 5);
    _retry = Timer(Duration(seconds: secs), () {
      _retry = null;
      _open();
    });
  }

  void disconnect() {
    _retry?.cancel();
    _retry = null;
    _diagramId = null;
    _token = null;
    _reconnecting = false;
    _attempt = 0;
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
    _connId = null;
  }

  void _send(Map<String, dynamic> payload) {
    _channel?.sink.add(jsonEncode(payload));
  }

  void requestLock(String classId) => _send({'action': 'lock', 'class_id': classId});
  void releaseLock(String classId) => _send({'action': 'unlock', 'class_id': classId});

  /// Suscribe un callback a un evento del diagrama. Devuelve una función
  /// para darse de baja (llamarla en dispose()/cuando cambie de pantalla).
  void Function() on(String event, RealtimeListener callback) {
    _listeners.putIfAbsent(event, () => []).add(callback);
    return () => _listeners[event]?.remove(callback);
  }

  void _emit(String event, Map<String, dynamic> data) {
    for (final cb in List<RealtimeListener>.from(_listeners[event] ?? const [])) {
      cb(data);
    }
  }
}
