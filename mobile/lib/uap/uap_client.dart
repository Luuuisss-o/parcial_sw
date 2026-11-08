// lib/uap/uap_client.dart
//
// Cliente HTTP contra el protocolo UAP de un backend Spring Boot GENERADO
// por el diagramador (ver exporters/generators/uap_generator.py). Distinto
// y separado de services/api_client.dart, que habla contra el backend
// FastAPI del diagramador en sí -- son dos backends de dominios
// completamente distintos, este cliente no sabe nada de "diagramas",
// "clases" ni "atributos" en el sentido del editor, solo de lo que UAP
// describe en runtime.
//
// A diferencia de ApiClient (que llama a http.get/http.post directo, sin
// forma de mockear sin tocar la red real), acá el http.Client se recibe
// por constructor: eso es lo que permite testear este cliente entero con
// package:http/testing.dart sin depender de un backend real corriendo.

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

import 'uap_config.dart';
import 'uap_manifest.dart';

class UapException implements Exception {
  final int statusCode;
  final String message;
  UapException(this.statusCode, this.message);
  @override
  String toString() => message;
}

class UapClient {
  final UapEndpoint endpoint;
  final http.Client _http;

  // Sin esto, una conexión que se cuelga en la capa de red (firewall,
  // adb reverse en mal estado, backend caído a mitad de respuesta) deja
  // el Future colgado para siempre -- y con él, cualquier UI que esté
  // esperando ese resultado (ej. ConnectionManager quedaba pegado en
  // "sincronizando" indefinidamente, sin error ni forma de recuperarse).
  static const _timeout = Duration(seconds: 10);

  UapClient(this.endpoint, {http.Client? httpClient}) : _http = httpClient ?? http.Client();

  Uri _u(String path, [Map<String, dynamic>? query]) =>
      Uri.parse('${endpoint.baseUrl}$path').replace(queryParameters: query?.map((k, v) => MapEntry(k, '$v')));

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        ...endpoint.extraHeaders,
      };

  Future<http.Response> _get(Uri url) => _http.get(url, headers: _headers).timeout(
        _timeout,
        onTimeout: () => throw UapException(0, 'El backend no respondió a tiempo. Verificá la conexión.'),
      );

  Future<http.Response> _post(Uri url, {required String body}) =>
      _http.post(url, headers: _headers, body: body).timeout(
        _timeout,
        onTimeout: () => throw UapException(0, 'El backend no respondió a tiempo. Verificá la conexión.'),
      );

  dynamic _decodeOrThrow(http.Response resp) {
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      if (resp.body.isEmpty) return null;
      return jsonDecode(resp.body);
    }
    String detail = 'El backend respondió con un error (${resp.statusCode}).';
    try {
      final data = jsonDecode(resp.body);
      if (data is Map && data['error'] != null) detail = '${data['error']}';
    } catch (_) {}
    throw UapException(resp.statusCode, detail);
  }

  Future<UapManifest> fetchManifest() async {
    final resp = await _get(_u('/uap/v1/manifest'));
    return UapManifest.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<List<UapTool>> fetchTools() async {
    final resp = await _get(_u('/uap/v1/tools'));
    final data = _decodeOrThrow(resp) as List;
    return data.map((t) => UapTool.fromJson(t as Map<String, dynamic>)).toList();
  }

  Future<Map<String, dynamic>> fetchSchema([String? entityKey]) async {
    final path = entityKey != null ? '/uap/v1/schema/$entityKey' : '/uap/v1/schema';
    final resp = await _get(_u(path));
    return _decodeOrThrow(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchPermissions() async {
    final resp = await _get(_u('/uap/v1/permissions'));
    return _decodeOrThrow(resp) as Map<String, dynamic>;
  }

  Future<List<String>> fetchBusinessRules() async {
    final resp = await _get(_u('/uap/v1/business-rules'));
    final data = _decodeOrThrow(resp) as List;
    return data.map((r) => r.toString()).toList();
  }

  /// Descubre manifest + tools en paralelo -- lo único que hace falta
  /// para armar un UapContract completo. El schema por entidad se pide
  /// aparte solo si hace falta detalle adicional que tools() no traiga.
  Future<UapContract> discover() async {
    final results = await Future.wait([fetchManifest(), fetchTools()]);
    return UapContract(manifest: results[0] as UapManifest, tools: results[1] as List<UapTool>);
  }

  Future<Map<String, dynamic>> invoke(
    String toolId,
    Map<String, dynamic> input, {
    required String clientRecordId,
  }) async {
    final resp = await _post(
      _u('/uap/v1/tools/$toolId/invoke'),
      body: jsonEncode({'clientRecordId': clientRecordId, 'input': input}),
    );
    return _decodeOrThrow(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncState() async {
    final resp = await _get(_u('/uap/v1/sync/state'));
    return _decodeOrThrow(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncChanges(int since, {String? generation}) async {
    final resp = await _get(
      _u('/uap/v1/sync/changes', {'since': since, if (generation != null) 'generation': generation}),
    );
    if (resp.statusCode == 409) {
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      return {'reset': true, 'generation': data['generation']};
    }
    return _decodeOrThrow(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncPush(List<Map<String, dynamic>> ops) async {
    final resp = await _post(_u('/uap/v1/sync/push'), body: jsonEncode({'ops': ops}));
    return _decodeOrThrow(resp) as Map<String, dynamic>;
  }

  void close() => _http.close();
}
