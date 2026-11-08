// lib/services/api_client.dart
//
// Cliente HTTP contra el mismo backend FastAPI que usa la versión web.
// Ninguna lógica de negocio vive acá adentro ni se duplica: esto es un
// espejo delgado de los endpoints, igual que frontend/src/api/*.js.

import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import '../models/diagram.dart';
import 'auth_service.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => message;
}

class ApiClient {
  final AuthService auth;
  ApiClient(this.auth);

  Uri _u(String path, [Map<String, dynamic>? query]) =>
      Uri.parse('${AppConfig.apiBaseUrl}$path').replace(
        queryParameters: query?.map((k, v) => MapEntry(k, '$v')),
      );

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (auth.token != null) 'Authorization': 'Bearer ${auth.token}',
      };

  dynamic _decodeOrThrow(http.Response resp) {
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      if (resp.body.isEmpty) return null;
      return jsonDecode(resp.body);
    }
    String detail = 'Error del servidor (${resp.statusCode})';
    try {
      final data = jsonDecode(resp.body);
      if (data is Map && data['detail'] != null) detail = '${data['detail']}';
    } catch (_) {}
    throw ApiException(resp.statusCode, detail);
  }

  // ---------------------------------------------------------------
  // Diagramas
  // ---------------------------------------------------------------

  Future<List<Diagram>> listDiagrams({int page = 1, int limit = 20}) async {
    final resp = await http.get(_u('/diagrams', {'page': page, 'limit': limit}), headers: _headers);
    final data = _decodeOrThrow(resp) as Map<String, dynamic>;
    return (data['items'] as List).map((d) => Diagram.fromJson(d as Map<String, dynamic>)).toList();
  }

  Future<Diagram> createDiagram(String title) async {
    final resp = await http.post(_u('/diagrams'), headers: _headers, body: jsonEncode({'title': title}));
    return Diagram.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<Diagram> getDiagram(String id) async {
    final resp = await http.get(_u('/diagrams/$id'), headers: _headers);
    return Diagram.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<void> deleteDiagram(String id) async {
    final resp = await http.delete(_u('/diagrams/$id'), headers: _headers);
    _decodeOrThrow(resp);
  }

  Future<List<Collaborator>> listCollaborators(String diagramId) async {
    final resp = await http.get(_u('/diagrams/$diagramId/collaborators'), headers: _headers);
    final data = _decodeOrThrow(resp) as List;
    return data.map((c) => Collaborator.fromJson(c as Map<String, dynamic>)).toList();
  }

  Future<Collaborator> addCollaborator(String diagramId, String email, {String role = 'EDITOR'}) async {
    final resp = await http.post(
      _u('/diagrams/$diagramId/collaborators'),
      headers: _headers,
      body: jsonEncode({'email': email, 'role': role}),
    );
    return Collaborator.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<void> removeCollaborator(String diagramId, int userId) async {
    final resp = await http.delete(_u('/diagrams/$diagramId/collaborators/$userId'), headers: _headers);
    _decodeOrThrow(resp);
  }

  // ---------------------------------------------------------------
  // Clases
  // ---------------------------------------------------------------

  Future<List<UmlClass>> listClasses(String diagramId) async {
    final resp = await http.get(_u('/diagrams/$diagramId/classes'), headers: _headers);
    final data = _decodeOrThrow(resp) as List;
    return data.map((c) => UmlClass.fromJson(c as Map<String, dynamic>)).toList();
  }

  Future<UmlClass> createClass(
    String diagramId,
    String name, {
    int? xGrid,
    int? yGrid,
    int? wGrid,
    int? hGrid,
  }) async {
    final resp = await http.post(
      _u('/diagrams/$diagramId/classes'),
      headers: _headers,
      body: jsonEncode({
        'name': name,
        if (xGrid != null) 'x_grid': xGrid,
        if (yGrid != null) 'y_grid': yGrid,
        if (wGrid != null) 'w_grid': wGrid,
        if (hGrid != null) 'h_grid': hGrid,
      }),
    );
    return UmlClass.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<UmlClass> updateClass(String classId, Map<String, dynamic> patch) async {
    final resp = await http.patch(_u('/diagrams/classes/$classId'), headers: _headers, body: jsonEncode(patch));
    return UmlClass.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<void> deleteClass(String classId) async {
    final resp = await http.delete(_u('/diagrams/classes/$classId'), headers: _headers);
    _decodeOrThrow(resp);
  }

  // ---------------------------------------------------------------
  // Atributos
  // ---------------------------------------------------------------

  Future<UmlAttribute> createAttribute(String classId, String name, String type, {bool required = false}) async {
    final resp = await http.post(
      _u('/diagrams/classes/$classId/attributes'),
      headers: _headers,
      body: jsonEncode({'name': name, 'type': type, 'required': required}),
    );
    return UmlAttribute.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<UmlAttribute> updateAttribute(String attrId, Map<String, dynamic> patch) async {
    final resp = await http.patch(_u('/diagrams/attributes/$attrId'), headers: _headers, body: jsonEncode(patch));
    return UmlAttribute.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<void> deleteAttribute(String attrId) async {
    final resp = await http.delete(_u('/diagrams/attributes/$attrId'), headers: _headers);
    _decodeOrThrow(resp);
  }

  // ---------------------------------------------------------------
  // Métodos
  // ---------------------------------------------------------------

  Future<UmlMethod> createMethod(String classId, String name, {String returnType = 'void'}) async {
    final resp = await http.post(
      _u('/diagrams/classes/$classId/methods'),
      headers: _headers,
      body: jsonEncode({'name': name, 'return_type': returnType}),
    );
    return UmlMethod.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<void> deleteMethod(String methodId) async {
    final resp = await http.delete(_u('/diagrams/methods/$methodId'), headers: _headers);
    _decodeOrThrow(resp);
  }

  // ---------------------------------------------------------------
  // Relaciones
  // ---------------------------------------------------------------

  Future<List<UmlRelation>> listRelations(String diagramId) async {
    final resp = await http.get(_u('/diagrams/$diagramId/relations'), headers: _headers);
    final data = _decodeOrThrow(resp) as List;
    return data.map((r) => UmlRelation.fromJson(r as Map<String, dynamic>)).toList();
  }

  Future<UmlRelation> createRelation({
    required String diagramId,
    required String fromClass,
    required String toClass,
    required RelationType type,
    String? label,
    int srcMultMin = 1,
    int? srcMultMax,
    int dstMultMin = 1,
    int? dstMultMax,
  }) async {
    final resp = await http.post(
      _u('/diagrams/$diagramId/relations'),
      headers: _headers,
      body: jsonEncode({
        'from_class': fromClass,
        'to_class': toClass,
        'type': relationTypeToApiString(type),
        if (label != null) 'label': label,
        'src_mult_min': srcMultMin,
        'src_mult_max': srcMultMax ?? '*',
        'dst_mult_min': dstMultMin,
        'dst_mult_max': dstMultMax ?? '*',
      }),
    );
    return UmlRelation.fromJson(_decodeOrThrow(resp) as Map<String, dynamic>);
  }

  Future<void> deleteRelation(String relationId) async {
    final resp = await http.delete(_u('/diagrams/relations/$relationId'), headers: _headers);
    _decodeOrThrow(resp);
  }
}
