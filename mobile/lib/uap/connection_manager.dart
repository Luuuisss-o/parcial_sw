// lib/uap/connection_manager.dart
//
// Orquesta cuándo sincronizar contra un backend UAP: escucha cambios de
// conectividad y de ciclo de vida de la app, evita disparar syncs
// simultáneos (single-flight), y reintenta con backoff cuando algo falla
// -- nunca hace polling agresivo contra el backend.

import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/widgets.dart';

import '../db/local_repository.dart';
import 'uap_client.dart';

enum UapConnectionState {
  conectado,
  desconectado,
  usandoDatosLocales,
  sincronizando,
  pendiente,
  conflicto,
  fallido,
}

/// Backoff fijo en segundos: 1, 2, 5, 10, 30 -- se reinicia con cada
/// sincronización exitosa. Función pura (no depende de instancia) para
/// que sea trivial de testear sin timers reales.
Duration backoffFor(int attempt) {
  const steps = [1, 2, 5, 10, 30];
  final index = attempt.clamp(0, steps.length - 1);
  return Duration(seconds: steps[index]);
}

class ConnectionManager extends ChangeNotifier with WidgetsBindingObserver {
  final UapClient client;
  final LocalRepository repo;
  final String entityKeysCsv; // entidades conocidas, para pedir sync/changes de todas

  ConnectionManager({required this.client, required this.repo, required List<String> entityKeys})
      : entityKeysCsv = entityKeys.join(',');

  UapConnectionState _state = UapConnectionState.desconectado;
  UapConnectionState get state => _state;

  int _attempt = 0;
  Future<void>? _inflight; // guardia single-flight
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  Timer? _retryTimer;

  void start() {
    WidgetsBinding.instance.addObserver(this);
    _connectivitySub = Connectivity().onConnectivityChanged.listen((results) {
      if (results.any((r) => r != ConnectivityResult.none)) {
        trySync();
      } else {
        _setState(UapConnectionState.desconectado);
      }
    });
    trySync();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) trySync();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivitySub?.cancel();
    _retryTimer?.cancel();
    super.dispose();
  }

  /// Dispara una sincronización si no hay una en curso -- si ya hay una,
  /// devuelve ese mismo Future en vez de arrancar una segunda
  /// (single-flight). Es lo que evita que un cambio de conectividad y un
  /// resume de la app disparen dos syncs al mismo tiempo.
  Future<void> trySync() {
    return _inflight ??= _runSync().whenComplete(() => _inflight = null);
  }

  Future<void> _runSync() async {
    _setState(UapConnectionState.sincronizando);
    try {
      final state = await client.syncState();
      final localGeneration = await repo.getMetadata('generation');
      final serverGeneration = state['generation'] as String?;

      if (localGeneration != null && serverGeneration != null && localGeneration != serverGeneration) {
        await repo.resetForNewGeneration(serverGeneration);
      } else if (serverGeneration != null) {
        await repo.setMetadata('generation', serverGeneration);
      }

      await _pushOutbox();
      await _pullChanges(serverGeneration);

      _attempt = 0;
      _setState(UapConnectionState.conectado);
    } catch (_) {
      _attempt++;
      _setState(UapConnectionState.fallido);
      _scheduleRetry();
    }
  }

  Future<void> _pushOutbox() async {
    final pending = await repo.pendingOps();
    if (pending.isEmpty) return;
    _setState(UapConnectionState.pendiente);

    final result = await client.syncPush([
      for (final op in pending)
        {'clientRecordId': op.clientRecordId, 'toolId': op.toolId, 'input': op.input},
    ]);

    final results = (result['results'] as List? ?? []);
    for (var i = 0; i < pending.length && i < results.length; i++) {
      final r = results[i] as Map<String, dynamic>;
      if (r['status'] == 'ok') {
        final body = r['result'] as Map<String, dynamic>? ?? {};
        final serverId = _extractServerId(body);
        if (serverId != null) await repo.confirmOp(pending[i].opId, serverId);
      } else {
        await repo.markOpFailed(pending[i].opId, r['result']?.toString() ?? 'error desconocido');
      }
    }
  }

  Future<void> _pullChanges(String? serverGeneration) async {
    final cursorStr = await repo.getMetadata('cursor') ?? '0';
    final cursor = int.tryParse(cursorStr) ?? 0;
    final result = await client.syncChanges(cursor, generation: serverGeneration);

    if (result['reset'] == true) {
      await repo.resetForNewGeneration(result['generation'] as String? ?? '');
      return;
    }

    final changes = (result['changes'] as List? ?? []);
    for (final c in changes) {
      final change = c as Map<String, dynamic>;
      await repo.applyServerChange(
        entityKey: change['entity'] as String,
        serverId: change['id'].toString(),
        op: change['op'] as String,
        record: change['record'] as Map<String, dynamic>?,
      );
    }
    if (result['cursor'] != null) await repo.setMetadata('cursor', result['cursor'].toString());
  }

  String? _extractServerId(Map<String, dynamic> body) {
    for (final value in body.values) {
      if (value is Map && value.containsKey('id')) return value['id'].toString();
    }
    return body['id']?.toString();
  }

  void _scheduleRetry() {
    _retryTimer?.cancel();
    _retryTimer = Timer(backoffFor(_attempt - 1), trySync);
  }

  void _setState(UapConnectionState s) {
    _state = s;
    notifyListeners();
  }
}
