# Contratos de API — parcial_sw

> Tabla por endpoint real, confirmado en los routers de `backend/app/routers/`. Shape de request/response resumido (no transcripción completa de schemas). Consumidor frontend = archivo en `frontend/src/api/`. Consumidor mobile = archivo en `mobile/lib/services/` (marcado "no confirmado" cuando no se leyó el archivo en detalle en este audit).

| Método | Path | Request (resumen) | Response (resumen) | Auth | Roles | Router/función | Service | Frontend (`src/api/`) | Mobile (`lib/services/`) |
|---|---|---|---|---|---|---|---|---|---|
| POST | `/auth/sign-in` | `{email, password}` | `{access_token, token_type, refresh_token?}` | No | — | `auth.sign_in` | — | no confirmado (no se leyó `api/auth.js` si existe) | `auth_service.dart` (no confirmado en detalle) |
| POST | `/diagrams` | `{title}` | `Diagram` (`id, title, updated_at, owner_id, owner_email`) | Sí | dueño | `diagramas.create_diagram` | — | `diagrams.js` (no leído en detalle) | `api_client.dart` (no confirmado) |
| GET | `/diagrams` | query `page, limit` | `{items: Diagram[], page, limit, total}` | Sí | dueño/colaborador | `diagramas.list_diagrams` | — | `diagrams.js` | `api_client.dart` |
| GET | `/diagrams/{id}` | — | `Diagram` | Sí | dueño/colaborador | `diagramas.get_diagram` | — | `diagrams.js` | `api_client.dart` |
| DELETE | `/diagrams/{id}` | — | 204 | Sí | dueño únicamente | `diagramas.delete_diagram` | — | `diagrams.js` | no confirmado |
| GET | `/diagrams/{id}/full` | — | `{id, title, clases: ClaseCompletaOut[], relaciones: RelacionOutExpanded[]}` | Sí | dueño/colaborador | `diagramas.get_diagram_full` | — | `diagrams.js` | `api_client.dart` |
| GET | `/diagrams/{id}/collaborators` | — | `CollaboratorOut[]` | Sí | dueño/colaborador | `diagramas.list_collaborators` | — | no confirmado (probable `collaborators.js` o similar, no visto en el glob) | no confirmado |
| POST | `/diagrams/{id}/collaborators` | `{email, role?}` | `CollaboratorOut` | Sí | dueño únicamente | `diagramas.add_collaborator` | — | ídem | no confirmado |
| DELETE | `/diagrams/{id}/collaborators/{user_id}` | — | 204 | Sí | dueño únicamente | `diagramas.remove_collaborator` | — | ídem | no confirmado |
| POST | `/diagrams/{id}/classes` | `ClaseCreate {name, x_grid?, y_grid?, w_grid?, h_grid?, z_index?}` | `ClaseCompletaOut` | Sí | dueño/colaborador | `classes.create_class` | `realtime_events` (notifica) | `classes.js` | `api_client.dart` (`createClass`) |
| GET | `/diagrams/classes/{class_id}` | — | `ClaseCompletaOut` | Sí | dueño/colaborador | `classes.get_class` | — | `classes.js` | `api_client.dart` |
| GET | `/diagrams/{id}/classes` | — | `ClaseCompletaOut[]` | Sí | dueño/colaborador | `classes.list_classes` | — | `classes.js` | `api_client.dart` (`listClasses`) |
| PATCH | `/diagrams/classes/{class_id}` | `ClaseUpdate` (parcial) | `ClaseCompletaOut` | Sí | dueño/colaborador | `classes.update_class` | `realtime_events` | `classes.js` | `api_client.dart` (`updateClass`) |
| DELETE | `/diagrams/classes/{class_id}` | — | 204 | Sí | dueño/colaborador | `classes.delete_class` | `realtime_events` | `classes.js` | `api_client.dart` (`deleteClass`) |
| GET | `/diagrams/classes/{class_id}/attributes` | — | `AtributoOut[]` | Sí | dueño/colaborador | `atributos.list_attributes` | — | no confirmado (probable `attributes.js`, no visto en glob explícito) | no confirmado |
| POST | `/diagrams/classes/{class_id}/attributes` | `{name, type, required?}` | `AtributoOut` | Sí | dueño/colaborador | `atributos.create_attribute` | `realtime_events` | ídem | `api_client.dart` (`createAttribute`) |
| PATCH | `/diagrams/attributes/{attr_id}` | parcial | `AtributoOut` | Sí | dueño/colaborador | `atributos.update_attribute` | `realtime_events` | ídem | no confirmado |
| DELETE | `/diagrams/attributes/{attr_id}` | — | `{id, class_id}` | Sí | dueño/colaborador | `atributos.delete_attribute` | `realtime_events` | ídem | `api_client.dart` (`deleteAttribute`) |
| GET | `/diagrams/classes/{class_id}/methods` | — | `MetodoOut[]` | Sí | dueño/colaborador | `metodo.list_methods` | — | no confirmado | no confirmado |
| POST | `/diagrams/classes/{class_id}/methods` | `{name, return_type?}` | `MetodoOut` | Sí | dueño/colaborador | `metodo.create_method` | `realtime_events` | no confirmado | `api_client.dart` (`createMethod`) |
| PATCH | `/diagrams/methods/{method_id}` | parcial | `MetodoOut` | Sí | dueño/colaborador | `metodo.update_method` | `realtime_events` | no confirmado | no confirmado |
| DELETE | `/diagrams/methods/{method_id}` | — | `{id, class_id}` | Sí | dueño/colaborador | `metodo.delete_method` | `realtime_events` | no confirmado | `api_client.dart` (`deleteMethod`) |
| POST | `/diagrams/{id}/relations` | `RelacionCreate {from_class, to_class, type, label?, anclajes?, multiplicidad?}` | `RelacionOut` | Sí | dueño/colaborador | `relacion.create_relation` | `realtime_events` | `relations.js` | `api_client.dart` (`createRelation`) |
| GET | `/diagrams/{id}/relations` | — | `RelacionOut[]` | Sí | dueño/colaborador | `relacion.list_relations` | — | `relations.js` | `api_client.dart` (`listRelations`) |
| PATCH | `/diagrams/relations/{relation_id}` | `RelacionUpdate` parcial | `RelacionOut` | Sí | dueño/colaborador | `relacion.update_relation` | `realtime_events` | `relations.js` | no confirmado |
| DELETE | `/diagrams/relations/{relation_id}` | — | 204 | Sí | dueño/colaborador | `relacion.delete_relation` | `realtime_events` | `relations.js` | `api_client.dart` (`deleteRelation`) |
| GET | `/diagrams/relations/{relation_id}` | — | dict con campos traducidos español→inglés | Sí | dueño/colaborador | `relacion.get_relation` | — | `relations.js` | no confirmado |
| POST | `/diagrams/{id}/export-download` | — | `application/zip` (FileResponse) | **No** (sin `get_current_user`) | ninguno exigido | `export.export_and_download` | `exporters/*` (módulo Python externo) | `export.js` (no leído en detalle) | no aplica (no hay Java en mobile) |
| POST | `/diagrams/{id}/ai/command` | `{text}` | 202 `{status: "processing"}` (resultado real por WS: `ai.done`/`ai.error`) | Sí | dueño/colaborador | `ai.ai_command` | `ai_assistant.run_command_background` → `ai_tools.DiagramToolExecutor` | `ai.js` (`sendAiCommand`) | `local_llm_service.dart` (equivalente local, no llama a este endpoint) |
| GET | `/diagrams/{id}/export-xmi` | — | `application/xml` (attachment) | Sí | dueño/colaborador | `xmi.export_xmi` | `services/xmi.build_xmi` | `xmi.js` (no leído en detalle) | no confirmado |
| POST | `/diagrams/{id}/import-xmi` | `multipart/form-data` (archivo .xmi) | `XmiImportSummary` | Sí | dueño/colaborador | `xmi.import_xmi` | `services/xmi.parse_xmi` + `ai_tools.DiagramToolExecutor` | `xmi.js` | no confirmado |
| POST | `/vision/detect` | `multipart/form-data` (imagen, JPEG/PNG/WEBP/HEIC, máx 10MB) | `VisionDetectResult {classes, relations, warning?}` | Sí | cualquier usuario autenticado | `vision.detect` | `services/diagram_vision.detect_from_image` | `vision.js` (`detectDiagramFromImage`, timeout 90s) | no aplica (no confirmado equivalente en mobile) |
| POST | `/vision/apply` | `VisionApplyIn {title, classes, relations}` | `VisionApplySummary {diagram_id, classes_created, attributes_created, relations_created, warnings}` | Sí | cualquier usuario autenticado (crea diagrama nuevo del que pasa a ser dueño) | `vision.apply` | `ai_tools.DiagramToolExecutor` | `vision.js` (`applyDetectedDiagram`) | no aplica |
| POST | `/voice/transcribe` (nuevo) | `multipart/form-data` (audio, WEBM/OGG/WAV/MP4/MPEG, máx 10MB) | `VoiceTranscribeResult {text}` | Sí | cualquier usuario autenticado | `voice.transcribe` | `services/voice_transcribe.transcribe_audio` (Gemini) | `voice.js` (`transcribeAudio`, timeout 45s) | no aplica — mobile usa Vosk offline (`speech_service.dart`), no este endpoint |
| WS | `/diagrams/{id}/ws` | query `?token=` + mensajes JSON (`lock`/`unlock`/`cursor`/`cursor_left`) | eventos JSON (`connected`, `locks.snapshot`, `class.locked`, `class.unlocked`, `lock.denied`, `cursor.move`, `cursor.left`, más eventos de dominio emitidos por `realtime_events` como `class.created`, `ai.done`, etc. — no enumerados exhaustivamente en este audit) | Sí (token en query string) | dueño/colaborador | `realtime.websocket_endpoint` | `services/locks.lock_manager`, `ws_manager` | `realtime.js` | `realtime_service.dart` |

## Notas de consistencia

- El endpoint `/voice/transcribe` sigue exactamente el mismo patrón de autenticación, límite de tamaño (10MB) y manejo de errores (503 si "mucha demanda", 400/502 en otros casos) que `/vision/detect` — son endpoints hermanos en diseño.
- `/diagrams/{id}/export-download` es la única ruta de recurso que **no exige autenticación** — inconsistente con el resto de la API. Ver también `CONTEXTO_BACKEND.md` y `ESTADO_ACTUAL.md`.
- Los campos de request/response de `relacion.py` (español en el modelo ORM: `origen_id`, `tipo`, `etiqueta`) se traducen a inglés en varios schemas de salida (`from_class`, `type`, `label`) pero no en el endpoint `GET /diagrams/relations/{relation_id}`, que construye un dict a mano con ambos estilos mezclados (`origen_nombre` en español, `from_class` en inglés) — confirmado leyendo `relacion.py` línea 233 en adelante.
