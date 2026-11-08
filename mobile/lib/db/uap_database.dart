// lib/db/uap_database.dart
//
// Apertura y esquema de la base SQLite offline-first para el cliente UAP.
// Cuatro tablas, siguiendo el diseño estandar de sync offline-first:
//
// - local_records: la copia local de cada registro (venga del servidor o
//   creado offline). localId es la clave primaria y NUNCA cambia -- es lo
//   que la UI usa para identificar una fila de forma estable, tanto si
//   todavia no tiene serverId (recien creada offline) como despues de
//   sincronizarse.
// - sync_outbox: la cola de operaciones pendientes de mandar al servidor.
//   clientRecordId = localId del registro que la origino, lo que da
//   idempotencia gratis: si se reintenta la misma fila del outbox, el
//   servidor (ver UapToolDispatcher.java, cache de idempotencia) devuelve
//   el mismo resultado sin duplicar nada.
// - sync_metadata: pares clave/valor para el estado de sincronizacion
//   (generation actual, cursor, ultima vez que se sincronizo).
// - identity_map: el puente localId<->serverId. Es la tabla que evita
//   crear una segunda fila la proxima vez que se ve el mismo serverId
//   (ver LocalRepository.applyServerChange).

import 'package:sqflite/sqflite.dart';

class UapDatabase {
  static const _dbName = 'uap_client.db';
  static const _dbVersion = 1;

  /// Ruta explícita del archivo de base de datos. Si es null (caso real de
  /// la app), se usa el directorio estándar de sqflite en el dispositivo.
  /// Los tests pasan `sqflite_common_ffi`'s `inMemoryDatabasePath` acá para
  /// que cada test corra sobre una base nueva y aislada, sin persistir
  /// nada entre corridas.
  final String? overridePath;

  UapDatabase({this.overridePath});

  Database? _db;

  Future<Database> open() async {
    if (_db != null) return _db!;
    final path = overridePath ?? '${await getDatabasesPath()}/$_dbName';
    _db = await openDatabase(
      path,
      version: _dbVersion,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE local_records (
            local_id      TEXT PRIMARY KEY,
            entity_key    TEXT NOT NULL,
            server_id     TEXT,
            payload_json  TEXT NOT NULL,
            state         TEXT NOT NULL,
            deleted       INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT NOT NULL,
            UNIQUE(entity_key, server_id)
          )
        ''');
        await db.execute('CREATE INDEX idx_local_records_entity ON local_records(entity_key, deleted)');

        await db.execute('''
          CREATE TABLE sync_outbox (
            op_id            TEXT PRIMARY KEY,
            local_id         TEXT NOT NULL,
            client_record_id TEXT NOT NULL,
            tool_id          TEXT NOT NULL,
            input_json       TEXT NOT NULL,
            attempts         INTEGER NOT NULL DEFAULT 0,
            last_error       TEXT,
            created_at       TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'pending'
          )
        ''');
        await db.execute('CREATE INDEX idx_outbox_pending ON sync_outbox(status, created_at)');

        await db.execute('''
          CREATE TABLE sync_metadata (
            key   TEXT PRIMARY KEY,
            value TEXT
          )
        ''');

        await db.execute('''
          CREATE TABLE identity_map (
            entity_key TEXT NOT NULL,
            local_id   TEXT NOT NULL,
            server_id  TEXT NOT NULL,
            PRIMARY KEY (entity_key, local_id),
            UNIQUE (entity_key, server_id)
          )
        ''');
      },
    );
    return _db!;
  }

  Future<void> close() async {
    await _db?.close();
    _db = null;
  }
}
