# Contexto para documentación académica UML — parcial_sw

> Insumo para que otra sesión futura genere la documentación académica completa (requisitos, actores, casos de uso, diagramas UML de clases/secuencia/comunicación/componentes/despliegue/estados/actividades/navegación, modelo conceptual/lógico/físico, arquitectura, C4, pruebas, docs de API/BD/frontend/backend/mobile, Scrum). Todo lo listado acá está verificado contra el código real. Se usan solo nombres reales de archivos/clases/endpoints/tablas — donde hace falta una abstracción de análisis que no es una clase real del código, se lo declara explícitamente como "elemento de análisis, no de implementación".

## Actores identificados (reales, según el modelo `User`/`Role` y el uso efectivo del sistema)

- **Usuario autenticado** (`User`, cualquier `role`): puede crear diagramas propios, editarlos, invitar colaboradores, usar el asistente de IA (texto/voz), importar fotos/XMI, exportar XMI/Spring Boot.
- **Dueño de diagrama** (`Diagram.owner_id == user.id`): además de lo anterior, puede eliminar el diagrama, agregar/quitar colaboradores.
- **Colaborador** (`DiagramCollaborator`, roles `EDITOR`/`VIEWER` — nota: el código valida acceso pero **no confirmado** que el rol `VIEWER` efectivamente bloquee escritura a nivel de endpoint; los routers usan `_accessible_diagram_filter` que no distingue EDITOR de VIEWER para permitir PATCH/POST, solo para permitir lectura/acceso. Esto es un hallazgo a verificar, no una funcionalidad confirmada).
- El campo `role` de `User` (`admin`/`editor`/`viewer`, enum `Role` en `models/user.py`) **no se usa en ninguna validación de autorización encontrada en los routers** — no confirmado que tenga efecto real hoy; se declara como "elemento de análisis, no de implementación activa" hasta que se confirme lo contrario.

## Casos de uso reales identificados

Para cada uno: código, nombre, actor, objetivo, precondiciones, flujo principal, flujos alternativos, postcondiciones, reglas de negocio, entidades/tablas/endpoints/controladores/servicios/componentes involucrados.

### CU-01 Login
- **Actor**: Usuario (no autenticado).
- **Objetivo**: obtener un JWT de acceso.
- **Precondiciones**: el usuario ya existe en la tabla `user` (no hay sign-up activo).
- **Flujo principal**: usuario envía `{email, password}` a `POST /auth/sign-in` → `auth.sign_in` busca por email, verifica con `verify_password` (bcrypt) → si es válido, `create_access_token` genera JWT (`sub=email`, `kind=access`) → responde `TokensOut`.
- **Flujo alternativo**: credenciales inválidas → 400 "Credenciales inválidas".
- **Postcondiciones**: el frontend guarda el token en `localStorage` (`store/auth.js`) y lo usa en cada request subsiguiente.
- **Entidades/tablas**: `user`. **Endpoint**: `POST /auth/sign-in`. **Controller**: `routers/auth.py`. **Service**: `core/security.py` (`verify_password`, `create_access_token`). **Frontend**: `pages/Login.jsx` llama directo a `api.post("/auth/sign-in", ...)` (confirmado: **no existe** un `api/auth.js` dedicado, es la única llamada de auth sin capa de servicio propia); guarda el token con `store/auth.js` (`login()`).
- **Relación con otros CU**: precondición de todos los demás CU (requieren `get_current_user`), excepto CU-11 (Exportar a Spring Boot), que no exige autenticación (hallazgo, ver `CONTRATOS_API.md`).

### CU-02 CRUD de diagrama
- **Actor**: Usuario autenticado (crear/listar/ver), Dueño (eliminar).
- **Objetivo**: crear, listar, ver y eliminar diagramas propios.
- **Endpoints**: `POST /diagrams`, `GET /diagrams`, `GET /diagrams/{id}`, `DELETE /diagrams/{id}`, `GET /diagrams/{id}/full`.
- **Controller**: `routers/diagramas.py`. **Entidad/tabla**: `diagram` (+ `clase`/`relacion` para `/full`). **Frontend**: `api/diagrams.js`, `pages/Home.jsx` (listado), `pages/Diagram.jsx` (editor).
- **Regla de negocio**: solo el dueño puede eliminar (`DELETE` filtra por `owner_id == me.id`, no por `_accessible_diagram_filter`).
- **Relación con otros CU**: base de CU-04, CU-05, CU-06, CU-07, CU-08, CU-09, CU-10, CU-11, CU-12, CU-13.

### CU-03 Gestión de colaboradores
- **Actor**: Dueño de diagrama.
- **Objetivo**: compartir un diagrama con otro usuario ya existente, asignándole rol EDITOR o VIEWER.
- **Precondiciones**: el usuario a invitar ya existe (no hay invitación por email a alguien no registrado).
- **Flujo principal**: `POST /diagrams/{id}/collaborators {email, role}` → busca el usuario destino por email → crea/actualiza `DiagramCollaborator`.
- **Flujo alternativo**: usuario destino no existe → 404; se intenta agregar al propio dueño → 400.
- **Endpoints**: `GET/POST /diagrams/{id}/collaborators`, `DELETE /diagrams/{id}/collaborators/{user_id}`.
- **Entidad/tabla**: `diagram_collaborator`. **Controller**: `routers/diagramas.py`. **Frontend**: confirmado en `api/diagrams.js` (`listCollaborators`, `addCollaborator`, `removeCollaborator` — mismo archivo que el CRUD de diagrama, no uno propio), consumido desde `components/panels/CollaboratorsModal.jsx`.
- **Relación con otros CU**: habilita que un colaborador acceda a CU-04 a CU-13 sobre ese diagrama.

### CU-04 CRUD de clase
- **Actor**: Usuario con acceso al diagrama (dueño o colaborador).
- **Objetivo**: crear, listar, ver, actualizar (nombre, posición/tamaño en grilla) y eliminar una clase.
- **Endpoints**: `POST /diagrams/{id}/classes`, `GET /diagrams/classes/{class_id}`, `GET /diagrams/{id}/classes`, `PATCH /diagrams/classes/{class_id}`, `DELETE /diagrams/classes/{class_id}`.
- **Entidad/tabla**: `clase`. **Controller**: `routers/classes.py`. **Service**: `utils/realtime_events` (notifica por WebSocket). **Frontend**: `api/classes.js`, `components/canvas/ClassCard/`.
- **Regla de negocio**: nombre de clase único por diagrama (validado en el router, `_ensure_unique_class_name`; **no hay constraint SQL** para esto, a diferencia de atributo/método).
- **Relación con otros CU**: precondición de CU-05, CU-06, CU-07; también ejecutable indirectamente desde CU-08 (asistente IA), CU-09/CU-10 (foto/XMI).

### CU-05 CRUD de atributo
- **Actor**: Usuario con acceso al diagrama.
- **Endpoints**: `GET/POST /diagrams/classes/{class_id}/attributes`, `PATCH/DELETE /diagrams/attributes/{attr_id}`.
- **Entidad/tabla**: `atributo` (constraint única `uq_atributo_clase_nombre`). **Controller**: `routers/atributos.py`. **Frontend**: confirmado en `api/classes.js` (`listAttributes`, `createAttribute`, `updateAttribute`, `deleteAttribute` — no hay un archivo `api/attributes.js` separado), consumido desde el inspector de clase (`components/panels/Inspector.jsx`).

### CU-06 CRUD de método
- Igual patrón que CU-05: `GET/POST /diagrams/classes/{class_id}/methods`, `PATCH/DELETE /diagrams/methods/{method_id}`. **Entidad**: `metodo`. **Controller**: `routers/metodo.py`. **Frontend**: confirmado en `api/classes.js` (`listMethods`, `createMethod`, `updateMethod`, `deleteMethod` — mismo archivo que clases y atributos, no uno propio).

### CU-07 CRUD de relación
- **Actor**: Usuario con acceso al diagrama.
- **Objetivo**: crear relaciones UML entre dos clases del mismo diagrama (ASSOCIATION/AGGREGATION/COMPOSITION/INHERITANCE/DEPENDENCY), con multiplicidad y anclajes visuales.
- **Endpoints**: `POST/GET /diagrams/{id}/relations`, `PATCH/DELETE/GET /diagrams/relations/{relation_id}`.
- **Entidad/tabla**: `relacion`. **Controller**: `routers/relacion.py`. **Frontend**: `api/relations.js`, `components/canvas/ConnectionLayer.jsx`, `components/panels/RelationInspector.jsx`.
- **Regla de negocio**: `DEPENDENCY`/`INHERITANCE` fuerzan multiplicidad `1..1` (validado en `schemas/relacion.py`).

### CU-08 Asistente de IA por texto
- **Actor**: Usuario con acceso al diagrama.
- **Objetivo**: editar el diagrama mediante instrucciones en lenguaje natural.
- **Precondiciones**: `GEMINI_API_KEY` configurada.
- **Flujo principal**: usuario escribe una instrucción en `AiAssistantPanel.jsx` → `POST /diagrams/{id}/ai/command {text}` → responde 202 de inmediato → `BackgroundTasks` ejecuta `ai_assistant.run_command_background` → Gemini decide qué tool(s) de `ai_tools.TOOLS` invocar → `DiagramToolExecutor` las ejecuta contra la base → cada acción dispara notificación WebSocket (igual que una edición manual) → al terminar, emite `ai.done {reply, actions}` o `ai.error {detail}` por WebSocket.
- **Flujo alternativo**: si el usuario pide que la IA diseñe un diagrama completo desde una descripción de negocio (sin nombrar clases concretas), el `SYSTEM_PROMPT` la instruye a negarse y pedir que se le indiquen las clases — regla de la cátedra.
- **Postcondiciones**: cambios aplicados y persistidos igual que si el usuario los hubiera hecho a mano.
- **Entidades/tablas**: `clase`, `atributo`, `metodo`, `relacion` (las mismas que CU-04/05/06/07). **Endpoint**: `POST /diagrams/{id}/ai/command`. **Controller**: `routers/ai.py`. **Service**: `services/ai_assistant.py` (orquestación + prompt), `services/ai_tools.py` (`DiagramToolExecutor`, definición de tools). **Frontend**: `components/panels/AiAssistantPanel.jsx`, `api/ai.js`.
- **Relación con otros CU**: comparte el mismo motor de ejecución (`DiagramToolExecutor`) que CU-09 (importar foto) y CU-10 (importar XMI).

### CU-08b Asistente de IA por voz (web) — NUEVO, código sin commitear
- **Actor**: Usuario con acceso al diagrama.
- **Objetivo**: dictar por voz una instrucción para el asistente, en vez de escribirla.
- **Precondiciones**: `GEMINI_API_KEY` configurada; navegador con soporte de `MediaRecorder`/`getUserMedia`; permiso de micrófono otorgado.
- **Flujo principal**: usuario presiona el botón de micrófono en `AiAssistantPanel.jsx` → `getUserMedia({audio:true})` → `MediaRecorder` graba → al presionar de nuevo, se arma un `Blob` → `transcribeAudio(blob)` (`api/voice.js`) → `POST /voice/transcribe` (multipart) → `voice.transcribe` valida mimetype/tamaño → `services/voice_transcribe.transcribe_audio` llama a Gemini (`gemini-3.5-flash`, fallback `gemini-3.5-flash-lite`) con reintentos ante 503 → devuelve `{text}` → el frontend llama a `send(text)`, que reutiliza exactamente el flujo de CU-08 (`sendAiCommand`).
- **Flujo alternativo**: sin soporte de micrófono → mensaje de error en el log del panel, sin llegar a grabar. Permiso denegado → mensaje de error. Audio vacío/silencio → 422 "No se entendió nada en el audio". Gemini saturado → 503 "mucha demanda", reintentado automáticamente 3 veces antes de fallar.
- **Postcondiciones**: el texto transcripto entra a CU-08 tal cual — este caso de uso **solo transcribe**, nunca aplica cambios directo al diagrama.
- **Entidades/tablas**: ninguna propia (no persiste nada). **Endpoint**: `POST /voice/transcribe`. **Controller**: `routers/voice.py`. **Service**: `services/voice_transcribe.py`. **Schema**: `schemas/voice.py`. **Frontend**: `components/panels/AiAssistantPanel.jsx` (función `toggleVoice`), `api/voice.js`.
- **Estado**: registrado en `main.py` (confirmado), **no probado en ejecución** en este audit — no confirmado si funciona end-to-end.
- **Relación con otros CU**: es un punto de entrada alternativo a CU-08; no reemplaza el input de texto, coexiste con él en el mismo panel.

### CU-08c Asistente de IA offline (mobile) — independiente de CU-08b
- **Actor**: Usuario de la app mobile.
- **Objetivo**: editar el diagrama por voz o texto sin conexión a internet.
- **Flujo principal**: `assistant_screen.dart` → `speech_service.dart` (Vosk) reconoce voz localmente → `local_llm_service.dart` (Qwen2.5-1.5B vía `llamadart`) decide una tool call → `_applyToolCall` en `assistant_screen.dart` la ejecuta llamando a `api_client.dart` contra el mismo backend REST (`createClass`, `createAttribute`, etc., no el endpoint de IA).
- **Diferencia clave con CU-08/CU-08b**: acá el modelo de IA que decide qué hacer corre en el teléfono, no en Gemini; y las operaciones se ejecutan como llamadas REST normales (CU-04/05/06/07), no a través de `POST /diagrams/{id}/ai/command`.
- **Entidades/tablas**: las mismas de siempre (`clase`, `atributo`, `metodo`, `relacion`), alcanzadas indirectamente. **Pantalla mobile**: `assistant_screen.dart`. **Servicios mobile**: `speech_service.dart`, `local_llm_service.dart`, `model_downloader.dart`.
- **Estado**: código completo, `android/` generado y `pubspec.lock` presente; compilación real **no confirmada**.

### CU-09 Importar diagrama desde foto
- **Actor**: Usuario autenticado.
- **Objetivo**: crear un diagrama nuevo a partir de una foto de un diagrama dibujado a mano.
- **Flujo principal**: `ImportFromPhotoModal.jsx` → `detectDiagramFromImage(file)` → `POST /vision/detect` (multipart) → `diagram_vision.detect_from_image` (Gemini Vision) devuelve `VisionDetectResult` **sin crear nada** → usuario revisa/corrige en el frontend → `applyDetectedDiagram(...)` → `POST /vision/apply` → crea un `Diagram` nuevo (el usuario pasa a ser dueño) y usa `DiagramToolExecutor` para crear cada clase/atributo/relación.
- **Flujo alternativo**: no se reconoce ninguna clase → 422. Relación con multiplicidad no parseable → se agrega a `warnings`, no aborta el resto.
- **Entidades/tablas**: `diagram`, `clase`, `atributo`, `relacion`. **Endpoints**: `POST /vision/detect`, `POST /vision/apply`. **Controller**: `routers/vision.py`. **Service**: `services/diagram_vision.py`, `services/ai_tools.py`. **Frontend**: `components/panels/ImportFromPhotoModal.jsx`, `api/vision.js`.

### CU-10 Exportar/Importar XMI
- **Actor**: Usuario con acceso al diagrama.
- **Objetivo**: interoperar con Enterprise Architect. **Disparado desde**: botones en `components/layout/HeaderBar.jsx` (props `onExportXmi`, `onImportXmiFile`); el estado de carga (`exportingXmi`/`importingXmi`) y los avisos de error/éxito se manejan en `pages/Diagram.jsx` (funciones `handleExportXmi`, `handleImportXmiFile`).
- **Flujo principal (export)**: `GET /diagrams/{id}/export-xmi` → `services/xmi.build_xmi` arma el XML → se descarga.
- **Flujo principal (import)**: sube un `.xmi` → `POST /diagrams/{id}/import-xmi` → `services/xmi.parse_xmi` → `DiagramToolExecutor` crea clases/atributos nuevos (omite duplicados, cuenta "skipped") y relaciones (idempotente por `(origen, destino, tipo)`).
- **Entidades/tablas**: `clase`, `atributo`, `relacion`. **Controller**: `routers/xmi.py`. **Frontend**: `api/xmi.js`.

### CU-11 Exportar a backend Spring Boot
- **Actor**: cualquiera que conozca el UUID del diagrama (**sin autenticación exigida** — hallazgo, ahora doblemente confirmado: el router no exige `get_current_user` Y `frontend/src/api/export.js` llama con `fetch` plano, sin adjuntar ningún header `Authorization` — a diferencia de `api/client.js`, que sí lo agrega vía interceptor a todos los demás endpoints).
- **Objetivo**: generar un proyecto Spring Boot completo y descargable a partir del diagrama. **Disparado desde**: botón en `components/layout/HeaderBar.jsx` (prop `onExport`).
- **Flujo principal**: `POST /diagrams/{id}/export-download` → `build_diagram_dict` arma un dict → `exporters.generators.uml_to_json.export_diagram_to_json` normaliza nombres a identificadores Java válidos y valida (`validator.py`) → `exporters.generators.project_builder.build_project` ejecuta el pipeline (`json_to_full_orm` → modelos JPA, `model_to_repository`, `repository_to_service`, `service_to_controller`, `model_to_dto`, `postman_generator`, + templates Jinja2 para `pom.xml`/`Dockerfile`/`docker-compose.yml`/etc.) → se comprime en ZIP → se devuelve como descarga.
- **Entidades/tablas involucradas (solo lectura)**: `diagram`, `clase`, `atributo`, `metodo`, `relacion`.
- **Controller**: `routers/export.py`. **Módulo externo**: `exporters/generators/*` (no auditado archivo por archivo en esta sesión, se documenta según lo ya descripto en `CONTEXTO_PROYECTO.md` original y confirmado por la lectura de `export.py`).
- **Nota de seguridad**: no exige `get_current_user` — cualquiera con el UUID puede descargar el proyecto generado. Confirmado leyendo el código del router.

### CU-12 Colaboración en tiempo real
- **Actor**: Usuario con acceso al diagrama (dueño o colaborador), múltiples simultáneos.
- **Objetivo**: ver cambios de otros usuarios en vivo, evitar edición simultánea de la misma clase, ver cursores de otros.
- **Flujo principal**: `WS /diagrams/{id}/ws?token=...` → autenticación por query string → al conectar recibe `connected` + `locks.snapshot` → cliente puede mandar `lock`/`unlock`/`cursor`/`cursor_left` → servidor hace broadcast de `class.locked`/`class.unlocked`/`cursor.move`/`cursor.left`, más los eventos de dominio (`class.created`, `attribute.updated`, `ai.done`, etc., emitidos por `realtime_events`, no enumerados exhaustivamente en este audit).
- **Regla de negocio**: exclusión mutua a nivel de clase individual, no de diagrama completo. Identificación por `conn_id` (por pestaña/conexión), no por email, para que la misma persona con dos pestañas no se bloquee a sí misma.
- **Controller**: `routers/realtime.py`. **Service**: `services/locks.py` (`lock_manager`), `ws_manager.py`. **Frontend**: confirmado en `api/realtime.js` — módulo con socket único (`connect`, `disconnect`, `requestLock`, `releaseLock`, `sendCursor`, `sendCursorLeft`, `onEvent`), no un hook; autenticación por query string (`?token=...`) porque el WebSocket nativo no admite headers custom. Consumido desde hooks del diagrama (`useLocks.js`/`useLiveCursors.js` en `pages/Diagram.jsx`, no auditados línea por línea en esta ronda). **Mobile**: `realtime_service.dart`.

### CU-13 Conversión a clase de asociación
- **Actor**: Usuario con acceso al diagrama.
- **Objetivo**: convertir una relación muchos-a-muchos en una clase de asociación explícita (UML 2.5).
- **Precondiciones**: existe una relación entre dos clases donde ambas multiplicidades quedaron en `*` (candidata detectada en `pages/Diagram.jsx`, variable `associationCandidate`).
- **Flujo principal**: `AssociationClassModal.jsx` solo muestra la explicación y pide confirmación — **no tiene endpoint propio** (confirmado leyendo el componente: no importa ningún cliente de `api/`). Al confirmar, dispara `convertToAssociationClass(relation)` en `pages/Diagram.jsx:322`, que: calcula una posición intermedia en la grilla → llama `createAssociationClass` (crea la clase intermedia, mismo endpoint que CU-04 `POST /diagrams/{id}/classes` con un helper propio) → llama `createRelation` (CU-07, `POST /diagrams/{id}/relations`) para conectar la clase intermedia con multiplicidad 1 a cada lado.
- **Flujo alternativo**: el usuario elige "Dejarla como está" → la relación queda muchos-a-muchos simple; al exportar a Spring Boot (CU-11) igual se genera la tabla intermedia vía `@JoinTable`, pero sin atributos propios posibles.
- **Entidades/tablas**: `clase`, `relacion` (mismas de CU-04 y CU-07, sin tabla ni endpoint propios). **Componente frontend**: `components/panels/AssociationClassModal.jsx` (solo UI de confirmación), orquestado desde `pages/Diagram.jsx`.
- **Relación con otros CU**: reutiliza CU-04 (crear clase) y CU-07 (crear relación); no es un caso de uso con backend propio, es una composición de dos ya existentes en la UI.

## Elementos de análisis, no de implementación (aclarado explícitamente)

- "Gestor de bloqueos" como concepto de diseño corresponde realmente a `services/locks.py::lock_manager`, una instancia concreta — no una clase de análisis abstracta separada.
- No se identificó ninguna clase de análisis genérica sin contraparte real (tipo "GestorEvento") en este código; todo lo listado arriba tiene un archivo/función real detrás.
- El "rol" de usuario (`admin`/`editor`/`viewer` en `User.role`) es un campo real en la tabla `user`, pero **no se confirmó que tenga efecto en ninguna regla de autorización actual** — para casos de uso que impliquen "solo un admin puede X", declarar explícitamente que no hay evidencia de esa restricción en el código y no inventarla.

## MATRIZ DE TRAZABILIDAD

CU → Actor → Pantalla/Componente → Servicio (frontend/mobile) → Endpoint → Controller (router) → Service (backend) → Repository/Model → Tabla

| CU | Actor | Pantalla/Componente | Servicio front/mobile | Endpoint | Controller | Service backend | Model | Tabla |
|---|---|---|---|---|---|---|---|---|
| CU-01 Login | Usuario | `pages/Login.jsx` | ninguno propio — `api.post` directo desde la página (confirmado: no existe `api/auth.js`) | `POST /auth/sign-in` | `routers/auth.py` | `core/security.py` | `User` | `user` |
| CU-02 CRUD diagrama | Usuario/Dueño | `pages/Home.jsx`, `pages/Diagram.jsx` | `api/diagrams.js` | `POST/GET/DELETE /diagrams`, `GET /diagrams/{id}/full` | `routers/diagramas.py` | — | `Diagram` | `diagram` |
| CU-03 Colaboradores | Dueño | `components/panels/CollaboratorsModal.jsx` | `api/diagrams.js` (confirmado: mismo archivo que CRUD de diagrama) | `GET/POST/DELETE /diagrams/{id}/collaborators*` | `routers/diagramas.py` | — | `DiagramCollaborator` | `diagram_collaborator` |
| CU-04 CRUD clase | Usuario con acceso | `components/canvas/ClassCard/` | `api/classes.js` | `POST/GET/PATCH/DELETE .../classes*` | `routers/classes.py` | `utils/realtime_events` | `Clase` | `clase` |
| CU-05 CRUD atributo | Usuario con acceso | `components/panels/Inspector.jsx` | `api/classes.js` (confirmado: mismo archivo que clases y métodos) | `GET/POST/PATCH/DELETE .../attributes*` | `routers/atributos.py` | `utils/realtime_events` | `Atributo` | `atributo` |
| CU-06 CRUD método | Usuario con acceso | `components/panels/Inspector.jsx` | `api/classes.js` (confirmado: mismo archivo) | `GET/POST/PATCH/DELETE .../methods*` | `routers/metodo.py` | `utils/realtime_events` | `Metodo` | `metodo` |
| CU-07 CRUD relación | Usuario con acceso | `components/canvas/ConnectionLayer.jsx`, `components/panels/RelationInspector.jsx` | `api/relations.js` | `POST/GET/PATCH/DELETE .../relations*` | `routers/relacion.py` | `utils/realtime_events` | `Relacion` | `relacion` |
| CU-08 Asistente IA texto | Usuario con acceso | `components/panels/AiAssistantPanel.jsx` | `api/ai.js` | `POST /diagrams/{id}/ai/command` | `routers/ai.py` | `services/ai_assistant.py`, `services/ai_tools.py` | `Clase`/`Atributo`/`Metodo`/`Relacion` | `clase`/`atributo`/`metodo`/`relacion` |
| CU-08b Asistente IA voz (web, nuevo) | Usuario con acceso | `components/panels/AiAssistantPanel.jsx` (función `toggleVoice`) | `api/voice.js` | `POST /voice/transcribe` (+ CU-08 después) | `routers/voice.py` | `services/voice_transcribe.py` | — (sin persistencia propia) | — |
| CU-08c Asistente IA offline (mobile) | Usuario mobile | `screens/assistant_screen.dart` | `services/speech_service.dart`, `services/local_llm_service.dart`, `services/api_client.dart` | endpoints de CU-04/05/06/07 (no el de IA) | `routers/classes.py`/`atributos.py`/`metodo.py`/`relacion.py` | `utils/realtime_events` | ídem | ídem |
| CU-09 Importar foto | Usuario | `components/panels/ImportFromPhotoModal.jsx` | `api/vision.js` | `POST /vision/detect`, `POST /vision/apply` | `routers/vision.py` | `services/diagram_vision.py`, `services/ai_tools.py` | `Diagram`/`Clase`/`Atributo`/`Relacion` | `diagram`/`clase`/`atributo`/`relacion` |
| CU-10 XMI | Usuario con acceso | Botones en `components/layout/HeaderBar.jsx` (confirmado: `onExportXmi`/`onImportXmiFile`), orquestado en `pages/Diagram.jsx` | `api/xmi.js` | `GET /diagrams/{id}/export-xmi`, `POST /diagrams/{id}/import-xmi` | `routers/xmi.py` | `services/xmi.py`, `services/ai_tools.py` | `Clase`/`Atributo`/`Relacion` | `clase`/`atributo`/`relacion` |
| CU-11 Exportar Spring Boot | Cualquiera con UUID (sin auth) | Botón en `components/layout/HeaderBar.jsx` (confirmado: prop `onExport`) | `api/export.js` (confirmado: usa `fetch` plano, sin header `Authorization`) | `POST /diagrams/{id}/export-download` | `routers/export.py` | `exporters/generators/*` (externo) | `Diagram`/`Clase`/`Atributo`/`Metodo`/`Relacion` (solo lectura) | `diagram`/`clase`/`atributo`/`metodo`/`relacion` |
| CU-12 Colaboración RT | Usuario con acceso | `components/canvas/Sheet.jsx` (cursores/locks visuales, no confirmado en detalle) | `api/realtime.js` (confirmado: módulo de socket único, no un hook) | `WS /diagrams/{id}/ws?token=...` | `routers/realtime.py` | `services/locks.py`, `ws_manager.py` | `Diagram`/`DiagramCollaborator` (para autorizar) | `diagram`/`diagram_collaborator` |
| CU-13 Clase de asociación | Usuario con acceso | `components/panels/AssociationClassModal.jsx` (solo confirmación UI), orquestado en `pages/Diagram.jsx` (`convertToAssociationClass`) | reutiliza `api/classes.js` (`createAssociationClass`) + `api/relations.js` (`createRelation`) — confirmado: sin servicio propio | reutiliza `POST /diagrams/{id}/classes` + `POST /diagrams/{id}/relations` (sin endpoint propio) | `routers/classes.py` + `routers/relacion.py` | `utils/realtime_events` | `Clase`/`Relacion` | `clase`/`relacion` |

**Notas de la matriz**: las celdas marcadas "no confirmado" requieren lectura adicional de archivos que no se auditaron línea por línea en esta sesión (fuera del alcance del pedido original, que se centró en la funcionalidad de voz y en verificar el resto del código a nivel de estructura). Una sesión futura dedicada a la documentación académica debería completar esas celdas antes de dibujar los diagramas de secuencia/comunicación de esos casos de uso específicos.
