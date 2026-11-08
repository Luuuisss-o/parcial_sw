import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:uml_collab_mobile/uap/uap_client.dart';
import 'package:uml_collab_mobile/uap/uap_config.dart';

void main() {
  group('UapEndpoint', () {
    test('modo usb usa usbBackendUrl y agrega header Host', () {
      const endpoint = UapEndpoint(UapConnectionMode.usb);
      expect(endpoint.baseUrl, UapConfig.usbBackendUrl);
      expect(endpoint.extraHeaders['Host'], UapConfig.backendHostHeader);
    });

    test('modo deployed usa deployedBackendUrl sin header Host', () {
      const endpoint = UapEndpoint(UapConnectionMode.deployed);
      expect(endpoint.baseUrl, UapConfig.deployedBackendUrl);
      expect(endpoint.extraHeaders.containsKey('Host'), false);
    });
  });

  group('UapClient.fetchManifest', () {
    test('parsea la respuesta y devuelve un UapManifest', () async {
      final mock = MockClient((request) async {
        expect(request.url.path, '/uap/v1/manifest');
        return http.Response(
          jsonEncode({
            'uapVersion': '1.0',
            'backendName': 'demo',
            'generation': 'g-1',
            'timezone': 'America/La_Paz',
            'entities': [
              {'key': 'producto', 'label': 'Producto', 'plural': 'productos', 'aliases': ['producto', 'productos'], 'idType': 'long'},
            ],
          }),
          200,
        );
      });
      final client = UapClient(const UapEndpoint(UapConnectionMode.deployed), httpClient: mock);
      final manifest = await client.fetchManifest();
      expect(manifest.backendName, 'demo');
      expect(manifest.entities, hasLength(1));
      expect(manifest.entities.first.key, 'producto');
    });

    test('modo USB manda el header Host esperado', () async {
      String? sentHost;
      final mock = MockClient((request) async {
        sentHost = request.headers['Host'];
        return http.Response(jsonEncode({'entities': []}), 200);
      });
      final client = UapClient(const UapEndpoint(UapConnectionMode.usb), httpClient: mock);
      await client.fetchManifest();
      expect(sentHost, UapConfig.backendHostHeader);
    });
  });

  group('UapClient.invoke', () {
    test('manda clientRecordId e input en el body', () async {
      Map<String, dynamic>? sentBody;
      final mock = MockClient((request) async {
        sentBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'ok': true}), 200);
      });
      final client = UapClient(const UapEndpoint(UapConnectionMode.deployed), httpClient: mock);
      await client.invoke('create_producto', {'nombre': 'Martillo'}, clientRecordId: 'abc-123');
      expect(sentBody?['clientRecordId'], 'abc-123');
      expect(sentBody?['input'], {'nombre': 'Martillo'});
    });

    test('404 se convierte en UapException con mensaje legible', () async {
      final mock = MockClient((request) async {
        return http.Response(jsonEncode({'error': 'toolId desconocido: create_x'}), 404);
      });
      final client = UapClient(const UapEndpoint(UapConnectionMode.deployed), httpClient: mock);
      expect(
        () => client.invoke('create_x', {}, clientRecordId: 'abc'),
        throwsA(isA<UapException>().having((e) => e.message, 'message', contains('toolId desconocido'))),
      );
    });
  });

  group('UapClient.syncChanges', () {
    test('409 con reset se traduce a un mapa reset:true sin lanzar', () async {
      final mock = MockClient((request) async {
        return http.Response(jsonEncode({'reset': true, 'generation': 'g-2'}), 409);
      });
      final client = UapClient(const UapEndpoint(UapConnectionMode.deployed), httpClient: mock);
      final result = await client.syncChanges(0, generation: 'g-1');
      expect(result['reset'], true);
      expect(result['generation'], 'g-2');
    });
  });

  group('UapClient.discover', () {
    test('combina manifest y tools en un UapContract', () async {
      final mock = MockClient((request) async {
        if (request.url.path.endsWith('/manifest')) {
          return http.Response(
            jsonEncode({'entities': [
              {'key': 'producto', 'aliases': ['producto', 'productos']},
            ]}),
            200,
          );
        }
        if (request.url.path.endsWith('/tools')) {
          return http.Response(
            jsonEncode([
              {'toolId': 'list_producto', 'entity': 'producto', 'description': '', 'inputSchema': {'properties': {}, 'required': []}},
            ]),
            200,
          );
        }
        return http.Response('not found', 404);
      });
      final client = UapClient(const UapEndpoint(UapConnectionMode.deployed), httpClient: mock);
      final contract = await client.discover();
      expect(contract.manifest.entities, hasLength(1));
      expect(contract.tools, hasLength(1));
      expect(contract.toolFor('list', 'producto')?.toolId, 'list_producto');
    });
  });
}
