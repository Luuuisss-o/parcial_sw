import 'package:flutter_test/flutter_test.dart';
import 'package:uml_collab_mobile/uap/intent_parser.dart';
import 'package:uml_collab_mobile/uap/uap_manifest.dart';

UapContract _tiendaContract() {
  final manifest = UapManifest(
    uapVersion: '1.0',
    backendName: 'tienda',
    generation: 'gen-1',
    timezone: 'America/La_Paz',
    entities: [
      UapEntity(key: 'cliente', label: 'Cliente', plural: 'clientes', aliases: ['cliente', 'clientes'], idType: 'long'),
      UapEntity(key: 'producto', label: 'Producto', plural: 'productos', aliases: ['producto', 'productos'], idType: 'long'),
    ],
  );
  final tools = [
    UapTool(
      toolId: 'create_producto',
      entityKey: 'producto',
      description: 'Crea un producto',
      properties: {
        'nombre': UapFieldSchema(type: 'string'),
        'precio': UapFieldSchema(type: 'number', format: 'decimal'),
        'stock': UapFieldSchema(type: 'integer'),
      },
      required: ['nombre', 'precio'],
    ),
    UapTool(
      toolId: 'list_producto',
      entityKey: 'producto',
      description: 'Lista productos',
      properties: {},
      required: [],
    ),
    UapTool(
      toolId: 'get_producto',
      entityKey: 'producto',
      description: 'Consulta un producto',
      properties: {'id': UapFieldSchema(type: 'integer')},
      required: ['id'],
    ),
    UapTool(
      toolId: 'delete_cliente',
      entityKey: 'cliente',
      description: 'Elimina un cliente',
      properties: {'id': UapFieldSchema(type: 'integer')},
      required: ['id'],
    ),
    UapTool(
      toolId: 'create_cliente',
      entityKey: 'cliente',
      description: 'Crea un cliente',
      properties: {
        'nombre': UapFieldSchema(type: 'string'),
        'activo': UapFieldSchema(type: 'boolean'),
      },
      required: ['nombre'],
    ),
  ];
  return UapContract(manifest: manifest, tools: tools);
}

void main() {
  late IntentParser parser;

  setUp(() {
    parser = IntentParser(_tiendaContract());
  });

  group('resolucion de entidad y verbo desde texto', () {
    test('crear con singular', () {
      final r = parser.parse('agregá un producto', draft: LlmDraft(fields: {'nombre': 'Martillo', 'precio': '50'}));
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).toolId, 'create_producto');
    });

    test('listar con plural', () {
      final r = parser.parse('listame los productos');
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).toolId, 'list_producto');
    });

    test('listar con singular igual resuelve', () {
      final r = parser.parse('lista de producto');
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).toolId, 'list_producto');
    });

    test('eliminar cliente con id', () {
      final r = parser.parse('borrá el cliente', draft: LlmDraft(fields: {'id': '3'}));
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).toolId, 'delete_cliente');
      expect(r.input['id'], 3);
    });

    test('entidad no reconocida se rechaza listando las validas', () {
      final r = parser.parse('creá un vehiculo');
      expect(r, isA<Rejected>());
      expect((r as Rejected).reasonEs, contains('Cliente'));
      expect(r.reasonEs, contains('Producto'));
    });

    test('sin verbo reconocible pide aclaracion', () {
      final r = parser.parse('el producto martillo');
      expect(r, isA<NeedsClarification>());
    });

    test('typo leve en la entidad se tolera (distancia 1)', () {
      final r = parser.parse('listar productoss'); // ya cubierto por plural real, probamos otro typo
      expect(r, isA<ParsedInvocation>());
    });
  });

  group('validacion de tools y campos contra el contrato', () {
    test('verbo valido pero sin esa tool para la entidad se rechaza', () {
      // "eliminar producto" no existe en el contrato de prueba (solo hay
      // create/list/get para producto, no delete).
      final r = parser.parse('eliminar producto', draft: LlmDraft(fields: {'id': '1'}));
      expect(r, isA<Rejected>());
      expect((r as Rejected).reasonEs, contains('no permite'));
    });

    test('campo desconocido propuesto por el LLM se rechaza sin ejecutar nada', () {
      final r = parser.parse(
        'crear producto',
        draft: LlmDraft(fields: {'nombre': 'Martillo', 'precio': '50', 'categoria_secreta': 'x'}),
      );
      expect(r, isA<Rejected>());
      expect((r as Rejected).reasonEs, contains('categoria_secreta'));
    });

    test('toolId inventado por el LLM nunca se usa directo -- se resuelve por texto', () {
      // Aunque el LLM proponga un entityHint que no exista, el parser cae
      // al analisis por texto antes de rendirse.
      final r = parser.parse('listar productos', draft: LlmDraft(entityHint: 'entidad_inventada'));
      expect(r, isA<ParsedInvocation>());
    });
  });

  group('sanitizacion de valores', () {
    test('rechaza una URL como valor de campo', () {
      final r = parser.parse(
        'crear producto',
        draft: LlmDraft(fields: {'nombre': 'http://evil.com/payload', 'precio': '10'}),
      );
      expect(r, isA<Rejected>());
    });

    test('rechaza un patron tipo SQL injection', () {
      final r = parser.parse(
        'crear producto',
        draft: LlmDraft(fields: {'nombre': "x'; DROP TABLE producto; --", 'precio': '10'}),
      );
      expect(r, isA<Rejected>());
    });

    test('rechaza un patron de shell injection', () {
      final r = parser.parse(
        'crear producto',
        draft: LlmDraft(fields: {'nombre': 'martillo && rm -rf /', 'precio': '10'}),
      );
      expect(r, isA<Rejected>());
    });

    test('rechaza un patron de reflexion Java', () {
      final r = parser.parse(
        'crear producto',
        draft: LlmDraft(fields: {'nombre': 'Class.forName("java.lang.Runtime")', 'precio': '10'}),
      );
      expect(r, isA<Rejected>());
    });

    test('un nombre de producto normal no se rechaza por error', () {
      final r = parser.parse(
        'crear producto',
        draft: LlmDraft(fields: {'nombre': 'Destornillador Phillips', 'precio': '25.50'}),
      );
      expect(r, isA<ParsedInvocation>());
    });
  });

  group('coercion integrada en el pipeline', () {
    test('precio con formato latino se coerciona antes de validar requeridos', () {
      final r = parser.parse('crear producto', draft: LlmDraft(fields: {'nombre': 'Tornillo', 'precio': '1.234,56'}));
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).input['precio'], '1234.56');
    });

    test('boolean en español se coerciona', () {
      final r = parser.parse('crear cliente', draft: LlmDraft(fields: {'nombre': 'Ana', 'activo': 'sí'}));
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).input['activo'], true);
    });

    test('valor no coercionable pide aclaracion en vez de rechazar', () {
      final r = parser.parse('crear producto', draft: LlmDraft(fields: {'nombre': 'Tornillo', 'precio': 'barato'}));
      expect(r, isA<NeedsClarification>());
    });
  });

  group('campos requeridos', () {
    test('falta un campo requerido pide aclaracion nombrandolo', () {
      final r = parser.parse('crear producto', draft: LlmDraft(fields: {'nombre': 'Tornillo'}));
      expect(r, isA<NeedsClarification>());
      expect((r as NeedsClarification).questionEs, contains('precio'));
    });

    test('campos opcionales ausentes no bloquean', () {
      final r = parser.parse('crear producto', draft: LlmDraft(fields: {'nombre': 'Tornillo', 'precio': '5'}));
      expect(r, isA<ParsedInvocation>());
      expect((r as ParsedInvocation).input.containsKey('stock'), false);
    });
  });

  test('texto vacio se rechaza de entrada', () {
    final r = parser.parse('   ');
    expect(r, isA<Rejected>());
  });

  group('charla casual (no debe sonar a error)', () {
    test('"hola" responde conversacional, no Rejected', () {
      final r = parser.parse('hola');
      expect(r, isA<Conversational>());
      expect((r as Conversational).replyEs, contains('Cliente'));
    });

    test('"buenas tardes" tambien es charla casual', () {
      final r = parser.parse('buenas tardes');
      expect(r, isA<Conversational>());
    });

    test('"gracias" responde conversacional', () {
      final r = parser.parse('gracias');
      expect(r, isA<Conversational>());
    });

    test('"que podes hacer" explica las operaciones disponibles', () {
      final r = parser.parse('que podes hacer');
      expect(r, isA<Conversational>());
      expect((r as Conversational).replyEs, contains('crear'));
    });

    test('"chau" se despide', () {
      final r = parser.parse('chau');
      expect(r, isA<Conversational>());
    });

    test('un pedido real sigue funcionando igual, no lo intercepta la charla casual', () {
      final r = parser.parse('listar productos');
      expect(r, isA<ParsedInvocation>());
    });
  });

  group('contexto conversacional (multi-turno)', () {
    test('solo la entidad, despues el verbo solo, completa la operacion', () {
      final r1 = parser.parse('producto');
      expect(r1, isA<NeedsClarification>());
      final context = (r1 as NeedsClarification).context;
      expect(context.entityKey, 'producto');

      final r2 = parser.parse('listar', previous: context);
      expect(r2, isA<ParsedInvocation>());
      expect((r2 as ParsedInvocation).toolId, 'list_producto');
    });

    test('el bug real reportado: entidad sola -> pregunta que querés hacer -> verbo solo', () {
      final r1 = parser.parse('cliente');
      expect(r1, isA<NeedsClarification>());
      final context = (r1 as NeedsClarification).context;
      expect(context.entityKey, 'cliente');

      final r2 = parser.parse('crear', previous: context, draft: LlmDraft(fields: {'nombre': 'Ana'}));
      expect(r2, isA<ParsedInvocation>());
      expect((r2 as ParsedInvocation).toolId, 'create_cliente');
    });

    test('con producto+crear recordados y solo falta el precio, se completa con el campo nuevo', () {
      final r1 = parser.parse('crear producto', draft: LlmDraft(fields: {'nombre': 'Tornillo'}));
      expect(r1, isA<NeedsClarification>());
      final context = (r1 as NeedsClarification).context;
      expect(context.fields['nombre'], 'Tornillo');

      final r2 = parser.parse('50', previous: context, draft: LlmDraft(fields: {'precio': '50'}));
      expect(r2, isA<ParsedInvocation>());
      final invocation = r2 as ParsedInvocation;
      expect(invocation.input['nombre'], 'Tornillo'); // no se perdió
      expect(invocation.input['precio'], '50');
    });

    test('mencionar una entidad nueva en el segundo turno la reemplaza, no se queda pegado a la primera', () {
      final r1 = parser.parse('cliente');
      final context = (r1 as NeedsClarification).context;
      expect(context.entityKey, 'cliente');

      final r2 = parser.parse('listar productos', previous: context);
      expect(r2, isA<ParsedInvocation>());
      expect((r2 as ParsedInvocation).toolId, 'list_producto'); // no quedó pegado a "cliente"
    });

    test('sin contexto previo (turno nuevo), "crear" solo sigue sin sentido', () {
      final r = parser.parse('crear');
      expect(r, isA<Rejected>());
    });
  });
}
