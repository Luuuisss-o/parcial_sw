# Contexto base de datos — parcial_sw

## Motor

PostgreSQL 16 (confirmado en `docker-compose.yml`: `image: postgres:16`).

## Tablas (confirmado en `backend/app/models/uml.py` y `user.py`, cruzado con las 3 migraciones Alembic)

### `user`
- `id` INTEGER PK.
- `email` VARCHAR(160), indexado (`ix_user_email`), **sin unique constraint** a nivel de columna en el modelo (no confirmado si hay una constraint agregada manualmente fuera de las migraciones vistas).
- `name` VARCHAR(120), `password_hash` VARCHAR(255).
- `role` ENUM `user_role` (`admin`, `editor`, `viewer`), default `editor`.
- `active` BOOLEAN, default `true`.
- `created_at`, `updated_at` TIMESTAMPTZ, default `now()`.

### `diagram`
- `id` UUID PK.
- `title` VARCHAR(200).
- `owner_id` INTEGER FK → `user.id` ON DELETE CASCADE.
- `updated_at` TIMESTAMPTZ, default/onupdate `now()`.
- Relaciones: 1 diagram → N `clase`, N `relacion`, N `diagram_collaborator` (todas cascade delete-orphan a nivel ORM, y ON DELETE CASCADE a nivel FK).

### `diagram_collaborator` (migración `3f9f653ec7cc`)
- `id` UUID PK.
- `diagram_id` UUID FK → `diagram.id` ON DELETE CASCADE, indexado.
- `user_id` INTEGER FK → `user.id` ON DELETE CASCADE, indexado.
- `role` ENUM `collaborator_role` (`EDITOR`, `VIEWER`), default `EDITOR`.
- `created_at` TIMESTAMPTZ default `now()`.
- Unique constraint `uq_diagram_collaborator_diagram_user` sobre `(diagram_id, user_id)`.

### `clase`
- `id` UUID PK.
- `nombre` VARCHAR(120).
- `diagram_id` UUID FK → `diagram.id` ON DELETE CASCADE, indexado.
- `x_grid`, `y_grid` INTEGER default 0; `w_grid` INTEGER default 12; `h_grid` INTEGER default 6; `z_index` INTEGER default 0.
- Relaciones: 1 clase → N `atributo`, N `metodo` (cascade); participa como origen/destino de N `relacion`.
- **Sin unique constraint a nivel de base de datos sobre `(diagram_id, nombre)`** — la unicidad de nombre de clase por diagrama se valida solo en el router (`_ensure_unique_class_name` en `classes.py`), no en el esquema SQL. Esto es una diferencia real respecto a `atributo`/`metodo`, que sí tienen la constraint en base de datos además de la validación en el router.

### `relacion`
- `id` UUID PK.
- `diagram_id` UUID FK → `diagram.id` ON DELETE CASCADE, indexado.
- `origen_id`, `destino_id` UUID FK → `clase.id` ON DELETE CASCADE.
- `tipo` ENUM (nombre de tipo Postgres: `reltype` en la migración inicial; el modelo Python usa el enum `RelType` con los mismos 5 valores: `ASSOCIATION`, `AGGREGATION`, `COMPOSITION`, `INHERITANCE`, `DEPENDENCY`).
- `etiqueta` VARCHAR(200), nullable.
- Anclajes visuales: `src_anchor`/`dst_anchor` VARCHAR(8) (default `right`/`left`), `src_offset`/`dst_offset` INTEGER default 0, `src_lane`/`dst_lane` INTEGER default 0.
- Multiplicidad: `mult_origen_min` INTEGER default 1, `mult_origen_max` INTEGER nullable (`NULL` = `*`), `mult_destino_min` INTEGER default 1, `mult_destino_max` INTEGER nullable (`NULL` = `*`).

### `atributo`
- `id` UUID PK.
- `nombre` VARCHAR(120), `tipo` VARCHAR(60) default `"string"` (tipo de dato libre, no un enum — el backend no restringe qué strings son válidos como tipo; la validación de "tipo Java válido" ocurre recién en el pipeline de `exporters/`, no en esta tabla).
- `requerido` BOOLEAN default `false`.
- `clase_id` UUID FK → `clase.id` ON DELETE CASCADE.
- Unique constraint `uq_atributo_clase_nombre` sobre `(clase_id, nombre)` (migración `cd269a313b01`).

### `metodo`
- `id` UUID PK.
- `nombre` VARCHAR(120), `tipo_retorno` VARCHAR(60) default `"void"`.
- `clase_id` UUID FK → `clase.id` ON DELETE CASCADE.
- Unique constraint `uq_metodo_clase_nombre` sobre `(clase_id, nombre)` (migración `cd269a313b01`).

## Relaciones entre tablas (resumen)

```
user (1) ──owner_id──> (N) diagram
user (1) ──user_id───> (N) diagram_collaborator <──diagram_id── (1) diagram
diagram (1) ──diagram_id──> (N) clase
diagram (1) ──diagram_id──> (N) relacion
clase (1) ──clase_id──> (N) atributo
clase (1) ──clase_id──> (N) metodo
clase (1) ──origen_id──> (N) relacion   (como origen)
clase (1) ──destino_id──> (N) relacion  (como destino)
```

## Migraciones (orden confirmado por `down_revision`, `backend/alembic/versions/`)

1. `a112c4d14f5b_init_schema.py` (sin down_revision, es la primera) — crea `user`, `diagram`, `clase`, `atributo`, `metodo`, `relacion` con sus columnas base, FKs e índices (`ix_user_email`, `ix_clase_diagram_id`, `ix_relacion_diagram_id`).
2. `cd269a313b01_add_unique_constraint_on_attribute_and_.py` (`down_revision = a112c4d14f5b`) — agrega `uq_atributo_clase_nombre` y `uq_metodo_clase_nombre`.
3. `3f9f653ec7cc_add_diagram_collaborators.py` (`down_revision = cd269a313b01`) — crea `diagram_collaborator` con sus índices y unique constraint.

No hay ninguna migración relacionada con la funcionalidad de voz — `voice.py`/`voice_transcribe.py` no persisten nada en base de datos, es transformación de audio→texto sin estado.

## Nombre de la base

`parcial_sw` (default de `POSTGRES_DB` en `docker-compose.yml`, override por variable de entorno `DB_NAME`). Puerto expuesto: `5433:5432` (mapeo host:contenedor).

## Relación entre tablas y funcionalidades

- CRUD de diagramas/clases/atributos/métodos/relaciones → tablas homónimas, vía los routers correspondientes.
- Colaboración (compartir diagrama) → `diagram_collaborator`.
- Asistente de IA (texto y voz) → no tiene tabla propia; opera sobre `clase`/`atributo`/`metodo`/`relacion` a través de `DiagramToolExecutor` (`ai_tools.py`), exactamente igual que si fuera un usuario editando a mano.
- Importar foto → crea un `diagram` nuevo + sus `clase`/`atributo`/`relacion`, vía el mismo `DiagramToolExecutor`.
- Importar/exportar XMI → lee/escribe sobre las mismas tablas, también vía `DiagramToolExecutor` para el import.
- Exportar a Spring Boot → **lectura únicamente** de `diagram`/`clase`/`atributo`/`metodo`/`relacion`; no escribe nada en esta base de datos (genera un proyecto Java aparte con su propio esquema JPA, que no comparte tablas con este Postgres).
