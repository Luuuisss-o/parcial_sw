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
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config.dart';

typedef RealtimeListener = void Function(Map<String, dynamic> data);

class RealtimeService {
  WebSocketChannel? _channel;
  String? _diagramId;
  String? _connId;
  StreamSubscription? _sub;

  final Map<String, List<RealtimeListener>> _listeners = {};

  String? get connId => _connId;
  bool get isConnected => _channel != null;

  void connect(String diagramId, String token) {
    if (_channel != null && _diagramId == diagramId) return;
    disconnect();

    _diagramId = diagramId;
    final uri = Uri.parse('${AppConfig.wsBaseUrl}/diagrams/$diagramId/ws?token=${Uri.encodeComponent(token)}');
    _channel = WebSocketChannel.connect(uri);

    _sub = _channel!.stream.listen(
      (raw) {
        Map<String, dynamic> msg;
        try {
          msg = jsonDecode(raw as String) as Map<String, dynamic>;
        } catch (_) {
          return;
        }
        final event = msg['event'] as String?;
        final data = (msg['data'] as Map?)?.cast<String, dynamic>() ?? {};
        if (event == 'connected') {
          _connId = data['conn_id'] as String?;
          return;
        }
        if (event != null) _emit(event, data);
      },
      onDone: () {
        _channel = null;
      },
      onError: (_) {
        _channel = null;
      },
    );
  }

  void disconnect() {
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
    _diagramId = null;
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
