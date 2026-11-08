# Contexto backend — parcial_sw

## Arquitectura

FastAPI, capas: `routers/` (HTTP) → lógica de negocio (inline en el router, o en `services/` cuando es no trivial) → `models/` (SQLAlchemy 2.0, `Mapped`/`mapped_column`) → PostgreSQL. Validación de entrada/salida con Pydantic v2 en `schemas/`. `routers/_helpers.py` centraliza `_accessible_diagram_filter(me)` (dueño o colaborador) y funciones `get_my_*` que resuelven y autorizan en un solo paso.

## Estructura de carpetas

```
backend/app/
├── routers/    auth.py, diagramas.py, classes.py, atributos.py, metodo.py,
│               relacion.py, export.py, ai.py, xmi.py, vision.py, voice.py (nuevo),
│               realtime.py (WebSocket), _helpers.py
├── models/     user.py (User, Role), uml.py (Diagram, DiagramCollaborator,
│               CollaboratorRole, Clase, Relacion, RelType, Atributo, Metodo)
├── schemas/    un archivo por recurso + voice.py (nuevo)
├── services/   ai_assistant.py, ai_tools.py, xmi.py, locks.py,
│               diagram_vision.py, voice_transcribe.py (nuevo)
├── core/       config.py (Settings), security.py (JWT + bcrypt)
├── db.py       (no leído en detalle en este audit — Base, SessionLocal, get_db)
├── ws_manager.py (no leído en detalle — gestor de conexiones WebSocket)
├── utils/realtime_events.py (no leído en detalle — helpers de notificación)
└── main.py     arma FastAPI, CORS, registra los 11 routers
```

## Entidades / modelos (`app/models/uml.py`, `app/models/user.py`)

- `User`: `id` (PK int), `email` (índice, sin unique constraint visible en el modelo), `name`, `password_hash`, `role` (enum `admin`/`editor`/`viewer`, default `editor`), `active` (default `true`), `created_at`, `updated_at`.
- `Diagram`: `id` (PK UUID), `title`, `owner_id` (FK `user.id` ON DELETE CASCADE), `updated_at`. Relaciones: `classes`, `relations`, `collaborators` (todas cascade delete-orphan). Property `owner_email`.
- `DiagramCollaborator`: `id` (PK UUID), `diagram_id` (FK), `user_id` (FK), `role` (enum `EDITOR`/`VIEWER`, default `EDITOR`), `created_at`. Unique constraint `(diagram_id, user_id)`.
- `Clase`: `id` (PK UUID), `nombre`, `diagram_id` (FK), layout (`x_grid`, `y_grid`, `w_grid` default 12, `h_grid` default 6, `z_index`). Relaciones `atributos`, `metodos` (cascade), `outgoing_relations`/`incoming_relations`.
- `Relacion`: `id` (PK UUID), `diagram_id`, `origen_id`/`destino_id` (FK a `clase.id`), `tipo` (enum `RelType`: ASSOCIATION/AGGREGATION/COMPOSITION/INHERITANCE/DEPENDENCY), `etiqueta`, anclajes visuales (`src_anchor`/`dst_anchor` default right/left, offsets, lanes), multiplicidad (`mult_origen_min` default 1, `mult_origen_max` nullable=`*`, ídem destino).
- `Atributo`: `id`, `nombre`, `tipo` (string libre, default "string"), `requerido` (bool), `clase_id` (FK). Unique `(clase_id, nombre)`.
- `Metodo`: `id`, `nombre`, `tipo_retorno` (default "void"), `clase_id` (FK). Unique `(clase_id, nombre)`.

## Schemas (Pydantic)

- `schemas/auth.py`: `SignUpIn` (existe, sin endpoint asociado), `SignInIn`, `UserOut`, `TokensOut`, `LoginResponse`.
- `schemas/clase.py` / `clase_completa.py`: `ClaseCreate`, `ClaseUpdate`, `ClaseOut` (alias `nombre`→`name`), `ClaseCompletaOut`/`ClaseCompletaOutLight` (con atributos/métodos anidados), `RelacionOutExpanded`.
- `schemas/atributo.py`, `schemas/metodo.py`: Create/Update/Out, sin alias (nombres ya en inglés en el modelo de request/response de estos routers específicos — inconsistente con `clase_completa.py` que sí usa alias).
- `schemas/relacion.py`: `RelacionCreate`/`RelacionUpdate` con validadores (`field_validator`, `model_validator`) para multiplicidad — fuerza `1..1` en DEPENDENCY/INHERITANCE, valida `max >= min`, acepta `"*"` como string y lo normaliza a `None` internamente y de vuelta a `"*"` en el output.
- `schemas/diagram.py`: `DiagramCreate`, `DiagramUpdate`, `DiagramOut`, `DiagramList`.
- `schemas/collaborator.py`: `CollaboratorCreate` (email + role default EDITOR), `CollaboratorOut`, `CollaboratorList`.
- `schemas/vision.py`: `DetectedAttribute`, `DetectedClass`, `DetectedRelation`, `VisionDetectResult`, `VisionApplyIn`, `VisionApplySummary`.
- `schemas/xmi.py`: `XmiImportSummary`.
- `schemas/ai.py`: `AiCommandIn` (`text`), `AiCommandAccepted` (`status`).
- `schemas/voice.py` (nuevo): `VoiceTranscribeResult` (`text: str`).

## Routers y endpoints (confirmados registrados en `main.py`)

| Router | Prefix | Endpoints |
|---|---|---|
| `auth.py` | `/auth` | `POST /auth/sign-in` (único endpoint de auth activo) |
| `diagramas.py` | `/diagrams` | `POST /diagrams`, `GET /diagrams`, `GET /diagrams/{id}`, `DELETE /diagrams/{id}`, `GET /diagrams/{id}/full`, `GET/POST /diagrams/{id}/collaborators`, `DELETE /diagrams/{id}/collaborators/{user_id}` |
| `classes.py` | `/diagrams` | `POST /diagrams/{id}/classes`, `GET /diagrams/classes/{class_id}`, `GET /diagrams/{id}/classes`, `PATCH /diagrams/classes/{class_id}`, `DELETE /diagrams/classes/{class_id}` |
| `atributos.py` | `/diagrams` | `GET/POST /diagrams/classes/{class_id}/attributes`, `PATCH/DELETE /diagrams/attributes/{attr_id}` |
| `metodo.py` | `/diagrams` | `GET/POST /diagrams/classes/{class_id}/methods`, `PATCH/DELETE /diagrams/methods/{method_id}` |
| `relacion.py` | `/diagrams` | `POST /diagrams/{id}/relations`, `GET /diagrams/{id}/relations`, `PATCH/DELETE/GET /diagrams/relations/{relation_id}` |
| `export.py` | `/diagrams` | `POST /diagrams/{id}/export-download` |
| `ai.py` | `/diagrams` | `POST /diagrams/{id}/ai/command` (202, `BackgroundTasks`) |
| `xmi.py` | `/diagrams` | `GET /diagrams/{id}/export-xmi`, `POST /diagrams/{id}/import-xmi` |
| `vision.py` | `/vision` | `POST /vision/detect`, `POST /vision/apply` |
| `voice.py` (nuevo) | `/voice` | `POST /voice/transcribe` |
| `realtime.py` | `/diagrams` | `WS /diagrams/{id}/ws` |

`GET /health` y `GET /` definidos directo en `main.py`.

## Autenticación y autorización

- Contraseñas: `bcrypt` (truncadas a 72 chars).
- JWT: `python-jose`, claims `sub` (email), `kind="access"`, `iat`, `exp`. Firmado con `JWT_SECRET`/`JWT_ALG` (default HS256).
- `get_current_user` (dependency): exige header `Authorization: Bearer`, valida `kind == "access"`, busca por email, verifica `active`.
- **Todos los routers de recursos exigen `get_current_user`, excepto `export.py`**: `POST /diagrams/{id}/export-download` no tiene `Depends(get_current_user)` ni valida `_accessible_diagram_filter` — cualquiera que conozca un UUID de diagrama puede exportarlo, autenticado o no. No confirmado si es intencional; se señala como hallazgo, no se corrige.
- El WebSocket (`realtime.py`) autentica por query string `?token=` (no por header), valida el mismo JWT y que el usuario tenga acceso al diagrama (dueño o colaborador).
- No hay refresh token implementado (`REFRESH_EXPIRE_DAYS` existe en `config.py` pero no se usa en ningún flujo).
- No hay endpoint de sign-up activo (`SignUpIn` existe en schemas, sin router).

## Validaciones y reglas de negocio

- Nombres de clase únicos por diagrama (`_ensure_unique_class_name`), de atributo único por clase (`_ensure_unique_attribute_name` + constraint DB `uq_atributo_clase_nombre`), de método único por clase (ídem, `uq_metodo_clase_nombre`).
- Multiplicidad: `RelacionCreate`/`RelacionUpdate` fuerzan `1..1` en relaciones `DEPENDENCY`/`INHERITANCE`; para el resto validan `max >= min`; aceptan `"*"` (sin cota).
- El asistente de IA (`ai_tools.py` + `ai_assistant.py`) resuelve clases/atributos/métodos por nombre (case-insensitive, `ilike`), no por UUID, porque el usuario le habla por nombre.
- El asistente de IA nunca genera el diagrama completo de una descripción de negocio (restricción de cátedra reforzada en el `SYSTEM_PROMPT`, ver `ai_assistant.py`).
- La detección de foto (`vision.py`) es de dos pasos: `/vision/detect` solo lee y devuelve, `/vision/apply` recién crea el diagrama.
- La transcripción de voz (`voice.py`, nuevo) es de un solo paso pero tampoco toca el diagrama directamente: devuelve texto plano que el frontend reenvía como comando a `/diagrams/{id}/ai/command`.
- Import de XMI es idempotente para relaciones (evita duplicar si se reimporta el mismo archivo), no para clases/atributos (usa `ToolError` para detectar "ya existe" y los cuenta como "skipped").

## Manejo de errores

- `ToolError` (en `ai_tools.py`): error esperado de una tool (ej. "no existe la clase X"), se le devuelve al modelo de IA para que corrija, o se traduce a un warning en vistas/imports.
- `describe_error(e)` (en `ai_assistant.py`): traduce excepciones del SDK de Gemini (por nombre de clase, ej. `RateLimitError` → mensaje en español) a un string legible; usado también por `vision.py` y `voice.py`.
- Los endpoints de foto y voz devuelven 503 si el mensaje de error contiene "mucha demanda" (Gemini saturado), 400 para otros `RuntimeError`, 502 para excepciones no anticipadas.
- El asistente de IA corre en `BackgroundTasks`: los errores no llegan como respuesta HTTP sino como evento WebSocket `ai.error`.

## Migraciones (`backend/alembic/versions/`, 3 archivos, orden confirmado por `down_revision`)

1. `a112c4d14f5b_init_schema.py` — esquema inicial: `user`, `diagram`, `clase`, `atributo`, `metodo`, `relacion`.
2. `cd269a313b01_add_unique_constraint_on_attribute_and_.py` — agrega `uq_atributo_clase_nombre` y `uq_metodo_clase_nombre`.
3. `3f9f653ec7cc_add_diagram_collaborators.py` — crea `diagram_collaborator`.

Ninguna migración nueva relacionada con voz — el endpoint `/voice/transcribe` no persiste nada en base de datos, es puramente transformación de audio a texto vía Gemini.

## Configuración (`app/core/config.py`)

`Settings` (pydantic-settings, lee `.env`): `DB_URL`, `JWT_SECRET`, `JWT_ALG` (default HS256), `ACCESS_EXPIRE_MIN` (default 480), `REFRESH_EXPIRE_DAYS` (default 14, sin uso real), `CORS_ORIGINS`, `DEBUG` (default False), `GEMINI_API_KEY` (default "", usado por `ai_assistant.py`, `diagram_vision.py` y `voice_transcribe.py`). Existe `backend/.env` (contenido no leído en este audit) y `backend/.env.example`.

## Archivos importantes nuevos (funcionalidad de voz)

- `backend/app/routers/voice.py` — endpoint HTTP.
- `backend/app/schemas/voice.py` — contrato de respuesta.
- `backend/app/services/voice_transcribe.py` — lógica de transcripción con Gemini, patrón de reintentos idéntico al de `diagram_vision.py`.
- `backend/app/main.py` (modificado) — registra `voice.router`.

## Estado actual

Confirmado por lectura de código: el router de voz está completo y registrado. No confirmado en ejecución (no se levantó el backend en esta sesión). El resto de los routers (auth, diagramas, classes, atributos, metodo, relacion, export, ai, xmi, vision, realtime) están implementados y no muestran cambios pendientes fuera de lo ya descripto.
