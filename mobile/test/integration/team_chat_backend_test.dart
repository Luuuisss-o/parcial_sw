// Prueba de integración del chat del equipo en el CELULAR contra el backend
// REAL (Fase 2): descarga del modelo personalizado (con reanudación y
// SHA-256), consulta "@IA" respondida en el dispositivo con la memoria
// híbrida del servidor, acciones aplicadas por REST y respuesta publicada
// para todo el equipo.
//
// Lo único simulado es la inferencia del modelo (en la VM de tests no hay
// llama.cpp ni un GGUF real): se reemplaza por una función que devuelve el
// texto que generaría el modelo personalizado, y se parsea con el mismo
// parser que usa la app.
//
//   cd backend && uvicorn app.main:app --port 8000      # con la base migrada y el seed
//   cd mobile && flutter test test/integration --dart-define=API_BASE_URL=http://127.0.0.1:8000
//
// Sin API_BASE_URL la prueba se saltea.

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uml_collab_mobile/config.dart';
import 'package:uml_collab_mobile/services/api_client.dart';
import 'package:uml_collab_mobile/services/assistant_prompt.dart';
import 'package:uml_collab_mobile/services/auth_service.dart';
import 'package:uml_collab_mobile/services/diagram_tool_runner.dart';
import 'package:uml_collab_mobile/services/local_team_assistant.dart';
import 'package:uml_collab_mobile/services/model_downloader.dart';

const _configured = bool.hasEnvironment('API_BASE_URL');

class _FakePaths extends PathProviderPlatform with MockPlatformInterfaceMixin {
  final String dir;
  _FakePaths(this.dir);
  @override
  Future<String?> getApplicationSupportPath() async => dir;
}

Future<String> _token(String email) async {
  final r = await http.post(Uri.parse('${AppConfig.apiBaseUrl}/auth/sign-in'),
      headers: {'Content-Type': 'application/json'}, body: jsonEncode({'email': email, 'password': 'admin123'}));
  return jsonDecode(r.body)['access_token'] as String;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  // El binding de tests bloquea la red; esta prueba necesita hablar con el backend real.
  HttpOverrides.global = null;

  late Directory phoneStorage;
  late ApiClient api;
  late String diagramId;
  late String adminToken;

  setUpAll(() async {
    if (!_configured) return;
    phoneStorage = await Directory.systemTemp.createTemp('telefono');
    PathProviderPlatform.instance = _FakePaths(phoneStorage.path);
    SharedPreferences.setMockInitialValues({});

    adminToken = await _token('ad1@example.com');
    final h = {'Authorization': 'Bearer $adminToken', 'Content-Type': 'application/json'};
    final d = await http.post(Uri.parse('${AppConfig.apiBaseUrl}/diagrams'),
        headers: h, body: jsonEncode({'title': 'Integración móvil (Fase 2)'}));
    diagramId = jsonDecode(d.body)['id'] as String;
    await http.post(Uri.parse('${AppConfig.apiBaseUrl}/diagrams/$diagramId/collaborators'),
        headers: h, body: jsonEncode({'email': 'ed2@example.com', 'role': 'EDITOR'}));

    // La app inicia sesión como Ana (colaboradora, no admin).
    final auth = AuthService();
    await auth.signIn('ed2@example.com', 'admin123');
    api = ApiClient(auth);
  });

  test('descarga el modelo personalizado del servidor, retomando una descarga cortada y verificando SHA-256', () async {
    // El "notebook de Colab" publica un modelo (solo el admin puede).
    final fakeGguf = [...utf8.encode('GGUF'), for (var i = 0; i < 300000; i++) i % 251];
    final req = http.MultipartRequest('PUT', Uri.parse('${AppConfig.apiBaseUrl}/models/assistant'))
      ..headers['Authorization'] = 'Bearer $adminToken'
      ..fields['version'] = '2026.11.08-test'
      ..fields['base_model'] = 'google/gemma-3-1b-it'
      ..files.add(http.MultipartFile.fromBytes('file', fakeGguf, filename: 'assistant.gguf'));
    expect((await req.send()).statusCode, 200);

    final dl = ModelDownloader();
    // Simula una descarga que se cortó a la mitad la vez anterior.
    final path = await dl.customModelPath();
    await File('$path.part').writeAsBytes(fakeGguf.sublist(0, 120000));

    final progress = <double>[];
    final manifest = await dl.syncCustomModel(api, onProgress: progress.add);
    expect(manifest!.version, '2026.11.08-test');
    expect(await File(path).readAsBytes(), fakeGguf);
    expect(sha256.convert(fakeGguf).toString(), manifest.sha256);
    expect(await dl.installedCustomVersion(), '2026.11.08-test');
    expect(progress.last, 1.0);
    // Segunda vez: ya está instalado, no se vuelve a descargar.
    await File(path).setLastModified(DateTime(2000));
    await dl.syncCustomModel(api, onProgress: (_) {});
    expect((await File(path).lastModified()).year, 2000);
  }, skip: !_configured);

  test('consulta @IA respondida en el celular: acciones reales y respuesta pública dirigida a quien preguntó', () async {
    final prompts = <String>[];
    // Lo que "generaría" el modelo personalizado: sin el nombre al principio
    // (para verificar que el servidor igual dirige la respuesta) y con
    // texto alrededor del JSON (como hacen los modelos chicos).
    Future<AssistantReply> fakeModel(Map<String, dynamic> ctx) async {
      prompts.add(formatGemmaChat(kTeamAssistantSystemPrompt, buildTeamAssistantUserMessage(ctx)));
      return parseAssistantReply('Listo:\n{"say": "creé Pago con monto y lo relacioné con Factura.", "actions": ['
          '{"tool": "create_class", "args": {"name": "Factura"}},'
          '{"tool": "create_class", "args": {"name": "Pago"}},'
          '{"tool": "add_attribute", "args": {"class_name": "Pago", "name": "monto", "type": "Double"}},'
          '{"tool": "create_relation", "args": {"from_class": "Factura", "to_class": "Pago", "type": "ASSOCIATION",'
          ' "src_multiplicity": "1", "dst_multiplicity": "0..*"}},'
          '{"tool": "add_attribute", "args": {"class_name": "NoExiste", "name": "x", "type": "String"}}]}');
    }

    final q = await api.sendChat(diagramId, '@IA creá Pago con monto y relacionalo con Factura',
        askAi: true, answerOnDevice: true);
    final runner = DiagramToolRunner(api, diagramId);
    await LocalTeamAssistant(
      fetchContext: (id) => api.questionContext(diagramId, id),
      model: fakeModel,
      runActions: runner.runAll,
      postAnswer: (id, {content, error, actions, aiMode, modelLabel}) => api.postDeviceAnswer(diagramId, id,
          content: content, error: error, actions: actions, aiMode: aiMode, modelLabel: modelLabel),
      modelLabel: () => 'Gemma 3 1B personalizado v2026.11.08-test (móvil)',
    ).answer(q.id);

    // El prompt del celular se armó con el contexto real del servidor.
    expect(prompts.single, contains('Quien pregunta: Ana Editor'));
    expect(prompts.single, contains('Consulta actual de Ana Editor: creá Pago con monto y relacionalo con Factura'));
    expect(prompts.single, startsWith('<start_of_turn>user\n$kTeamAssistantSystemPrompt'));

    // Las acciones se aplicaron de verdad (por REST, como cualquier edición).
    final classes = await api.listClasses(diagramId);
    expect(classes.map((c) => c.name), containsAll(['Factura', 'Pago']));
    expect(classes.firstWhere((c) => c.name == 'Pago').attributes.single.name, 'monto');
    final rel = (await api.listRelations(diagramId)).single;
    expect(rel.toClassId, classes.firstWhere((c) => c.name == 'Pago').id);

    // La respuesta quedó en el chat para todo el equipo, dirigida a Ana,
    // con el modelo que la generó y avisando la acción que falló.
    final answer = (await api.listChat(diagramId)).last;
    expect(answer.role, 'ASSISTANT');
    expect(answer.replyToId, q.id);
    expect(answer.addressedToName, 'Ana Editor');
    expect(answer.content, startsWith('Ana, creé Pago'));
    expect(answer.content, contains('No pude aplicar todo'));
    expect(answer.actionsCount, 4);
    expect(answer.aiModelLabel, 'Gemma 3 1B personalizado v2026.11.08-test (móvil)');
  }, skip: !_configured);

  test('consulta teórica en el celular: mentoría sin tocar el diagrama aunque el modelo proponga acciones', () async {
    final before = (await api.listClasses(diagramId)).length;
    final q = await api.sendChat(diagramId, '@IA no me acuerdo qué es un atributo derivado',
        askAi: true, answerOnDevice: true);
    await LocalTeamAssistant(
      fetchContext: (id) => api.questionContext(diagramId, id),
      model: (_) async => parseAssistantReply('{"say": "Ana, un atributo derivado se calcula a partir de otros '
          '(en UML lleva /). Ej: /total en Factura.", "actions": [{"tool": "delete_class", "args": {"class_name": "Pago"}}]}'),
      runActions: DiagramToolRunner(api, diagramId).runAll,
      postAnswer: (id, {content, error, actions, aiMode, modelLabel}) => api.postDeviceAnswer(diagramId, id,
          content: content, error: error, actions: actions, aiMode: aiMode, modelLabel: modelLabel),
      modelLabel: () => 'Gemma (móvil)',
    ).answer(q.id);

    expect((await api.listClasses(diagramId)).length, before);
    final answer = (await api.listChat(diagramId)).last;
    expect(answer.aiMode, 'MENTOR');
    expect(answer.content, startsWith('Ana, un atributo derivado'));
  }, skip: !_configured);
}
