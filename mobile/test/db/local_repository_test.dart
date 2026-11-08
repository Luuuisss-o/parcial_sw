import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:uml_collab_mobile/db/local_repository.dart';
import 'package:uml_collab_mobile/db/uap_database.dart';

void main() {
  // sqflite normalmente necesita el plugin nativo de Android/iOS; en el
  // test runner de escritorio (donde corren estos tests) se reemplaza el
  // factory por la implementación FFI, que sí puede correr acá. Esto
  // permite testear SQLite real (no un mock) sin un dispositivo.
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late UapDatabase uapDb;
  late LocalRepository repo;

  setUp(() {
    // Base en memoria, nueva por test: evita que datos de un test
    // "contaminen" el siguiente (con un archivo en disco compartido, un
    // UNIQUE constraint de un test anterior puede hacer fallar al
    // siguiente sin que el codigo de produccion tenga ningun bug).
    uapDb = UapDatabase(overridePath: inMemoryDatabasePath);
    repo = LocalRepository(uapDb);
  });

  tearDown(() async {
    await uapDb.close();
  });

  test('createLocal genera un local_id estable y encola en el outbox', () async {
    final localId = await repo.createLocal(
      entityKey: 'producto',
      toolId: 'create_producto',
      input: {'nombre': 'Martillo'},
    );
    expect(localId, isNotEmpty);

    final record = await repo.getLocal(localId);
    expect(record, isNotNull);
    expect(record!.state, 'pending');
    expect(record.serverId, isNull);
    expect(record.payload['nombre'], 'Martillo');

    final pending = await repo.pendingOps();
    expect(pending, hasLength(1));
    expect(pending.first.localId, localId);
    expect(pending.first.clientRecordId, localId); // idempotencia: clientRecordId = localId
  });

  test('listLocal no incluye registros eliminados (tombstone)', () async {
    final localId = await repo.createLocal(entityKey: 'producto', toolId: 'create_producto', input: {'nombre': 'X'});
    await repo.deleteLocal(localId: localId, toolId: 'delete_producto');

    final list = await repo.listLocal('producto');
    expect(list, isEmpty);

    // Pero el registro sigue existiendo internamente (tombstone, no
    // borrado fisico) -- se puede seguir consultando por id.
    final record = await repo.getLocal(localId);
    expect(record, isNotNull);
    expect(record!.deleted, true);
  });

  test('updateLocal permite editar el mismo registro antes de sincronizar', () async {
    final localId = await repo.createLocal(entityKey: 'producto', toolId: 'create_producto', input: {'nombre': 'X', 'precio': '10'});
    await repo.updateLocal(localId: localId, toolId: 'update_producto', input: {'precio': '20'});

    final record = await repo.getLocal(localId);
    expect(record!.payload['nombre'], 'X'); // se conserva
    expect(record.payload['precio'], '20'); // se actualiza

    final pending = await repo.pendingOps();
    expect(pending, hasLength(2)); // create + update, ambas en el outbox
  });

  test('confirmOp marca synced y crea la entrada en identity_map', () async {
    final localId = await repo.createLocal(entityKey: 'producto', toolId: 'create_producto', input: {'nombre': 'X'});
    final op = (await repo.pendingOps()).first;

    await repo.confirmOp(op.opId, '42');

    final record = await repo.getLocal(localId);
    expect(record!.state, 'synced');
    expect(record.serverId, '42');

    final pending = await repo.pendingOps();
    expect(pending, isEmpty); // la op ya no esta pendiente
  });

  test('confirmOp es idempotente: confirmar la misma op dos veces no duplica identity_map', () async {
    final localId = await repo.createLocal(entityKey: 'producto', toolId: 'create_producto', input: {'nombre': 'X'});
    final op = (await repo.pendingOps()).first;

    await repo.confirmOp(op.opId, '42');
    await repo.confirmOp(op.opId, '42'); // reintento tardio del mismo resultado

    final record = await repo.getLocal(localId);
    expect(record!.serverId, '42');
    // No debe haber lanzado ni haber creado una segunda fila -- se
    // verifica indirectamente listando: sigue habiendo un solo producto.
    final list = await repo.listLocal('producto');
    expect(list, hasLength(1));
  });

  test('applyServerChange con un serverId nuevo crea UN solo registro local', () async {
    await repo.applyServerChange(entityKey: 'producto', serverId: '7', op: 'CREATE', record: {'id': 7, 'nombre': 'Del server'});
    final list = await repo.listLocal('producto');
    expect(list, hasLength(1));
    expect(list.first.serverId, '7');
  });

  test('applyServerChange con el MISMO serverId dos veces no duplica -- reconciliacion', () async {
    await repo.applyServerChange(entityKey: 'producto', serverId: '7', op: 'CREATE', record: {'id': 7, 'nombre': 'Version 1'});
    await repo.applyServerChange(entityKey: 'producto', serverId: '7', op: 'UPDATE', record: {'id': 7, 'nombre': 'Version 2'});

    final list = await repo.listLocal('producto');
    expect(list, hasLength(1)); // sigue siendo UN registro, no dos
    expect(list.first.payload['nombre'], 'Version 2'); // con el dato actualizado
  });

  test('applyServerChange con op DELETE marca el registro como eliminado', () async {
    await repo.applyServerChange(entityKey: 'producto', serverId: '7', op: 'CREATE', record: {'id': 7, 'nombre': 'X'});
    await repo.applyServerChange(entityKey: 'producto', serverId: '7', op: 'DELETE');

    final list = await repo.listLocal('producto');
    expect(list, isEmpty);
  });

  test('resetForNewGeneration purga registros synced pero conserva el outbox pendiente', () async {
    // Un registro ya sincronizado (vino del servidor).
    await repo.applyServerChange(entityKey: 'producto', serverId: '1', op: 'CREATE', record: {'id': 1, 'nombre': 'Viejo'});
    // Y un registro creado offline, todavia sin confirmar.
    final pendingLocalId = await repo.createLocal(entityKey: 'producto', toolId: 'create_producto', input: {'nombre': 'Nuevo offline'});

    await repo.resetForNewGeneration('generation-2');

    final list = await repo.listLocal('producto');
    // El sincronizado viejo desaparece (era de la generation anterior)...
    expect(list.any((r) => r.serverId == '1'), false);
    // ...pero el pendiente offline SIGUE, porque es trabajo del usuario
    // que no depende de que generation era la base vieja.
    expect(list.any((r) => r.localId == pendingLocalId), true);

    final pending = await repo.pendingOps();
    expect(pending, hasLength(1));
    expect(pending.first.localId, pendingLocalId);

    expect(await repo.getMetadata('generation'), 'generation-2');
    expect(await repo.getMetadata('cursor'), '0');
  });

  test('markOpFailed incrementa attempts y mantiene la op pendiente para reintentar', () async {
    await repo.createLocal(entityKey: 'producto', toolId: 'create_producto', input: {'nombre': 'X'});
    final op = (await repo.pendingOps()).first;

    await repo.markOpFailed(op.opId, 'timeout de red');

    final stillPending = await repo.pendingOps();
    expect(stillPending, hasLength(1));
    expect(stillPending.first.attempts, 1);
  });
}
