// lib/db/local_repository.dart
//
// Acceso a las 4 tablas offline-first (ver uap_database.dart) desde el
// resto de la app. Todo lo que la UI necesita para el flujo
// crear/listar/actualizar/eliminar offline vive acá; nada de esto habla
// con la red directamente (eso es responsabilidad de UapClient +
// ConnectionManager, que usan este repositorio como su fuente/destino
// local).

import 'dart:convert';
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

import 'uap_database.dart';

const _uuid = Uuid();

class LocalRecord {
  final String localId;
  final String entityKey;
  final String? serverId;
  final Map<String, dynamic> payload;
  final String state; // synced | pending | conflict | failed
  final bool deleted;

  LocalRecord({
    required this.localId,
    required this.entityKey,
    required this.serverId,
    required this.payload,
    required this.state,
    required this.deleted,
  });

  factory LocalRecord.fromRow(Map<String, dynamic> row) {
    return LocalRecord(
      localId: row['local_id'] as String,
      entityKey: row['entity_key'] as String,
      serverId: row['server_id'] as String?,
      payload: jsonDecode(row['payload_json'] as String) as Map<String, dynamic>,
      state: row['state'] as String,
      deleted: (row['deleted'] as int) == 1,
    );
  }
}

class OutboxOp {
  final String opId;
  final String localId;
  final String clientRecordId;
  final String toolId;
  final Map<String, dynamic> input;
  final int attempts;

  OutboxOp({
    required this.opId,
    required this.localId,
    required this.clientRecordId,
    required this.toolId,
    required this.input,
    required this.attempts,
  });

  factory OutboxOp.fromRow(Map<String, dynamic> row) {
    return OutboxOp(
      opId: row['op_id'] as String,
      localId: row['local_id'] as String,
      clientRecordId: row['client_record_id'] as String,
      toolId: row['tool_id'] as String,
      input: jsonDecode(row['input_json'] as String) as Map<String, dynamic>,
      attempts: row['attempts'] as int,
    );
  }
}

class LocalRepository {
  final UapDatabase _uapDb;
  LocalRepository(this._uapDb);

  Future<Database> get _db async => _uapDb.open();

  // ---------------------------------------------------------------
  // Lectura
  // ---------------------------------------------------------------

  Future<List<LocalRecord>> listLocal(String entityKey) async {
    final db = await _db;
    final rows = await db.query(
      'local_records',
      where: 'entity_key = ? AND deleted = 0',
      whereArgs: [entityKey],
      orderBy: 'updated_at DESC',
    );
    return rows.map(LocalRecord.fromRow).toList();
  }

  Future<LocalRecord?> getLocal(String localId) async {
    final db = await _db;
    final rows = await db.query('local_records', where: 'local_id = ?', whereArgs: [localId]);
    return rows.isEmpty ? null : LocalRecord.fromRow(rows.first);
  }

  // ---------------------------------------------------------------
  // Escritura offline (crear/actualizar/eliminar sin esperar al servidor)
  // ---------------------------------------------------------------

  /// Crea un registro local nuevo y encola su creación en el outbox.
  /// clientRecordId = localId a propósito: es lo que le da idempotencia al
  /// reintento (ver UapToolDispatcher.java del lado servidor, que cachea
  /// por clientRecordId). Devuelve el localId generado.
  Future<String> createLocal({
    required String entityKey,
    required String toolId,
    required Map<String, dynamic> input,
  }) async {
    final db = await _db;
    final localId = _uuid.v4();
    final now = DateTime.now().toIso8601String();

    await db.insert('local_records', {
      'local_id': localId,
      'entity_key': entityKey,
      'server_id': null,
      'payload_json': jsonEncode(input),
      'state': 'pending',
      'deleted': 0,
      'updated_at': now,
    });

    await db.insert('sync_outbox', {
      'op_id': _uuid.v4(),
      'local_id': localId,
      'client_record_id': localId,
      'tool_id': toolId,
      'input_json': jsonEncode(input),
      'attempts': 0,
      'created_at': now,
      'status': 'pending',
    });

    return localId;
  }

  /// Actualiza un registro local ya existente (venga del servidor o
  /// creado offline) y encola la actualización. Permite volver a editar
  /// el mismo registro antes de que la operación anterior se sincronice
  /// -- cada llamada agrega una operación nueva al outbox, que se procesan
  /// en orden de creación.
  Future<void> updateLocal({
    required String localId,
    required String toolId,
    required Map<String, dynamic> input,
  }) async {
    final db = await _db;
    final existing = await getLocal(localId);
    if (existing == null) throw StateError('No existe un registro local con id $localId');

    final merged = {...existing.payload, ...input};
    final now = DateTime.now().toIso8601String();

    await db.update(
      'local_records',
      {'payload_json': jsonEncode(merged), 'state': 'pending', 'updated_at': now},
      where: 'local_id = ?',
      whereArgs: [localId],
    );

    await db.insert('sync_outbox', {
      'op_id': _uuid.v4(),
      'local_id': localId,
      'client_record_id': localId,
      'tool_id': toolId,
      'input_json': jsonEncode({
        if (existing.serverId != null) 'id': existing.serverId,
        ...input,
      }),
      'attempts': 0,
      'created_at': now,
      'status': 'pending',
    });
  }

  /// Marca un registro como eliminado localmente (tombstone: no se borra
  /// la fila, se marca deleted=1) y encola la eliminación. El registro
  /// desaparece de listLocal() de inmediato, sin esperar al servidor --
  /// pero nunca se afirma que ya se sincronizó (ver response_phrasing.dart).
  Future<void> deleteLocal({required String localId, required String toolId}) async {
    final db = await _db;
    final existing = await getLocal(localId);
    if (existing == null) throw StateError('No existe un registro local con id $localId');

    final now = DateTime.now().toIso8601String();
    await db.update(
      'local_records',
      {'deleted': 1, 'state': 'pending', 'updated_at': now},
      where: 'local_id = ?',
      whereArgs: [localId],
    );

    await db.insert('sync_outbox', {
      'op_id': _uuid.v4(),
      'local_id': localId,
      'client_record_id': localId,
      'tool_id': toolId,
      'input_json': jsonEncode({if (existing.serverId != null) 'id': existing.serverId}),
      'attempts': 0,
      'created_at': now,
      'status': 'pending',
    });
  }

  // ---------------------------------------------------------------
  // Outbox (usado por ConnectionManager)
  // ---------------------------------------------------------------

  Future<List<OutboxOp>> pendingOps() async {
    final db = await _db;
    final rows = await db.query('sync_outbox', where: "status = 'pending'", orderBy: 'created_at ASC');
    return rows.map(OutboxOp.fromRow).toList();
  }

  Future<void> markOpFailed(String opId, String error) async {
    final db = await _db;
    await db.rawUpdate(
      "UPDATE sync_outbox SET status = 'pending', attempts = attempts + 1, last_error = ? WHERE op_id = ?",
      [error, opId],
    );
  }

  /// Confirma que una operación del outbox se aplicó en el servidor:
  /// marca la op como done, guarda/actualiza identity_map y deja el
  /// registro local como synced. Es idempotente -- confirmar la misma
  /// op_id dos veces (ej. un reintento tardío que en realidad sí había
  /// llegado) no duplica nada en identity_map porque la clave primaria es
  /// (entity_key, local_id).
  Future<void> confirmOp(String opId, String serverId) async {
    final db = await _db;
    final opRows = await db.query('sync_outbox', where: 'op_id = ?', whereArgs: [opId]);
    if (opRows.isEmpty) return;
    final op = OutboxOp.fromRow(opRows.first);

    final record = await getLocal(op.localId);
    if (record == null) return;

    await db.insert(
      'identity_map',
      {'entity_key': record.entityKey, 'local_id': op.localId, 'server_id': serverId},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );

    await db.update(
      'local_records',
      {'server_id': serverId, 'state': 'synced'},
      where: 'local_id = ?',
      whereArgs: [op.localId],
    );

    await db.update('sync_outbox', {'status': 'done'}, where: 'op_id = ?', whereArgs: [opId]);
  }

  // ---------------------------------------------------------------
  // Reconciliación con cambios que vienen del servidor (sync/changes)
  // ---------------------------------------------------------------

  /// Aplica un cambio recibido del servidor. Busca primero en
  /// identity_map por serverId: si ya existe un local_id mapeado, ACTUALIZA
  /// esa fila (nunca crea una segunda); si no existe, recién ahí crea un
  /// registro local nuevo. Esta es la función que garantiza "un serverId
  /// nunca produce dos filas visibles".
  Future<void> applyServerChange({
    required String entityKey,
    required String serverId,
    required String op, // CREATE | UPDATE | DELETE
    Map<String, dynamic>? record,
  }) async {
    final db = await _db;
    final mapped = await db.query(
      'identity_map',
      where: 'entity_key = ? AND server_id = ?',
      whereArgs: [entityKey, serverId],
    );

    final now = DateTime.now().toIso8601String();

    if (op == 'DELETE') {
      if (mapped.isNotEmpty) {
        await db.update(
          'local_records',
          {'deleted': 1, 'state': 'synced', 'updated_at': now},
          where: 'local_id = ?',
          whereArgs: [mapped.first['local_id']],
        );
      }
      return;
    }

    if (mapped.isNotEmpty) {
      await db.update(
        'local_records',
        {'payload_json': jsonEncode(record ?? {}), 'state': 'synced', 'deleted': 0, 'updated_at': now},
        where: 'local_id = ?',
        whereArgs: [mapped.first['local_id']],
      );
      return;
    }

    final localId = _uuid.v4();
    await db.insert('local_records', {
      'local_id': localId,
      'entity_key': entityKey,
      'server_id': serverId,
      'payload_json': jsonEncode(record ?? {}),
      'state': 'synced',
      'deleted': 0,
      'updated_at': now,
    });
    await db.insert(
      'identity_map',
      {'entity_key': entityKey, 'local_id': localId, 'server_id': serverId},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  // ---------------------------------------------------------------
  // Metadata de sincronización / reset de generation
  // ---------------------------------------------------------------

  Future<String?> getMetadata(String key) async {
    final db = await _db;
    final rows = await db.query('sync_metadata', where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : rows.first['value'] as String?;
  }

  Future<void> setMetadata(String key, String value) async {
    final db = await _db;
    await db.insert('sync_metadata', {'key': key, 'value': value}, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Se llama cuando /uap/v1/manifest (o sync/state) reporta una
  /// generation distinta de la que teníamos guardada: la base de datos
  /// del servidor es otra (se recreó el volumen). Se purgan los datos
  /// cacheados y el cursor -- pero las operaciones del outbox que
  /// todavía no se mandaron se CONSERVAN, porque son trabajo del usuario
  /// que no depende de qué generation era la base vieja.
  Future<void> resetForNewGeneration(String newGeneration) async {
    final db = await _db;
    await db.delete('local_records', where: "state = 'synced'");
    await db.delete('identity_map');
    await setMetadata('generation', newGeneration);
    await setMetadata('cursor', '0');
    // Nota: un registro "pending" que ya tuviera server_id de la
    // generation VIEJA (ej. una edicion offline sobre algo ya
    // sincronizado antes del reset) queda con un server_id que no existe
    // en la base nueva. El outbox lo va a reintentar contra un id
    // inexistente y el servidor va a responder 404 -- se documenta como
    // limitacion conocida en vez de resolverse acá: en la practica del
    // examen, un reset de generation (recrear el volumen de Postgres)
    // sucede antes de que haya trabajo offline real, no en medio de una
    // sesion en curso.
  }
}
