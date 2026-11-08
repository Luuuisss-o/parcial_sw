# Contexto del proyecto — parcial_sw

> Documento para que una sesión nueva de Claude Code (u otro asistente) entienda el proyecto sin depender del historial de conversaciones previas. Todo lo escrito acá está verificado contra el código real al momento de escribirlo. Donde no se pudo confirmar algo con evidencia, se indica explícitamente en vez de asumir.

## 1. Objetivo del proyecto

Editor colaborativo de diagramas de clases UML, desarrollado para un examen de Ingeniería de Software. Permite:

- Crear y editar diagramas de clases en tiempo real, con varios usuarios trabajando sobre el mismo diagrama a la vez (colaboración vía WebSocket).
- Crear un diagrama a mano en papel/pizarra, sacarle una foto, y que el sistema lo transcriba a un diagrama digital (usando Gemini Vision).
- Editar el diagrama con un asistente de IA por texto (Gemini), con un contrato fijo de "tools" (crear clase, agregar atributo, crear relación, etc.) — nunca genera un diseño completo desde una descripción de negocio, solo ejecuta ediciones puntuales que pide el usuario.
- Importar y exportar el diagrama en formato XMI 2.1, compatible con Enterprise Architect.
- **Generar un backend Spring Boot completo y funcional** a partir del diagrama: modelos JPA, repositorios, servicios, controladores REST, DTOs, colección Postman, Dockerfile y docker-compose — listo para compilar y correr.
- Una app móvil (Flutter, en desarrollo) pensada para el día del examen, con un asistente de IA que corre 100% offline en el teléfono (sin depender de Gemini ni de internet).

El alcance NO incluye: registro de usuarios desde la UI (no hay endpoint de sign-up activo, ver sección 5), refresh tokens (no implementado pese a existir la configuración), ni ejecución del backend Spring Boot generado dentro de este mismo proyecto (se descarga y se levanta aparte).

## 2. Arquitectura

```
Usuario (navegador o app móvil)
      │
      ├── frontend (React, puerto 5173) ──┐
      │                                    │  REST + WebSocket
      └── mobile (Flutter, sin puerto fijo)┘  (mismo backend para ambos)
                     │
                     ▼
      backend (FastAPI, puerto 8000)
                     │
      ┌──────────────┼───────────────────────────┐
      ▼              ▼                           ▼
PostgreSQL      Gemini (Google AI)          exporters/ (módulo Python
puerto 5433     asistente de texto,         interno, corre en el mismo
                lectura de fotos            proceso del backend)
                                                   │
                                                   ▼
                                    genera un ZIP: proyecto Spring Boot
                                    + Dockerfile + docker-compose.yml
                                    + colección Postman + README
                                                   │
                                                   ▼
                                    usuario lo descomprime y lo levanta
                                    aparte (Spring Boot puerto 8090,
                                    su propio Postgres puerto 5434)
```

El frontend en producción (Docker) sirve los archivos estáticos con nginx, que hace proxy de `/api/` hacia el backend (`frontend/nginx.conf`). El navegador nunca le habla directo al backend en el puerto 8000 cuando corre en Docker; en desarrollo local (`npm run dev`), sí.

No hay otros servicios externos además de Gemini (Google AI) para el asistente de IA y la lectura de fotos.

## 3. Tecnologías

**Backend**: Python, FastAPI, SQLAlchemy 2.0, Alembic (migraciones), Pydantic v2 (`pydantic-settings`), `python-jose` (JWT), `passlib` con bcrypt (hash de contraseñas), `google-genai` (cliente de Gemini). Base de datos: PostgreSQL 16.

**Frontend**: React 19, Vite, `react-router-dom` (ruteo), `axios` (cliente HTTP), `zustand` (estado global). Servido en producción con nginx.

**Exporters**: Python puro + Jinja2 (para renderizar templates `.j2` de Java/YAML/properties). Genera código **Java 17 + Spring Boot 3.2.4** (Maven, `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, driver `org.postgresql`).

**Mobile**: Flutter/Dart. Paquetes clave: `http`, `web_socket_channel`, `provider`, `shared_preferences`, `llamadart` (LLM local vía llama.cpp), `vosk_flutter_2` (reconocimiento de voz offline).

**Infraestructura**: Docker + Docker Compose para el diagramador completo y, por separado, para cada backend Spring Boot exportado.

## 4. Estructura del proyecto

```
parcial_sw/
├── backend/            API FastAPI: routers, modelos ORM, schemas, seguridad, migraciones
│   ├── app/
│   │   ├── routers/     endpoints REST y el WebSocket
│   │   ├── models/      modelos SQLAlchemy (uml.py, user.py)
│   │   ├── schemas/     schemas Pydantic (uno por recurso)
│   │   ├── services/    lógica de negocio no trivial (IA, XMI, locks, visión)
│   │   ├── core/        config y seguridad (JWT, hashing)
│   │   └── main.py      arma la app FastAPI y registra los routers
│   ├── alembic/          migraciones de base de datos
│   ├── seeds/            carga de datos demo opcional (SEED_DEMO=true)
│   ├── postman/          colección Postman del propio backend FastAPI del diagramador (distinta de la que genera exporters/ para el Spring Boot exportado)
│   └── scripts/          openapi_to_postman.py, regenera la colección de arriba desde el schema OpenAPI del backend
│
├── frontend/            editor visual en React
│   └── src/
│       ├── pages/        Login, Home (lista de diagramas), Diagram (el editor)
│       ├── components/   canvas/ (lienzo y tarjetas de clase), panels/ (inspectores y modales), layout/, common/
│       ├── hooks/         lógica de estado por feature (clases, relaciones, locks, cursores, auto-guardado)
│       ├── api/            un archivo por recurso, todos usan el cliente de api/client.js
│       └── store/          zustand: auth.js (sesión), locks.js, undo.js
│
├── exporters/            generador de backend Spring Boot a partir del diagrama
│   ├── generators/        un archivo Python por etapa del pipeline (ver sección 9)
│   └── templates/         plantillas Jinja2 (.j2) para los archivos que no dependen del diagrama (pom.xml, Dockerfile, etc.)
│
├── mobile/               app Flutter (sin compilar todavía, ver sección 7)
│   └── lib/
│       ├── screens/        pantallas
│       ├── services/       API, WebSocket, auth, IA local, voz, descarga de modelos
│       └── models/         espejo de los schemas del backend
│
└── docker-compose.yml    levanta backend + frontend + Postgres del diagramador (sin trackear en git todavía)
```

## 5. Backend

### Arquitectura
FastAPI con capas: `routers/` (HTTP) → `services/`/lógica inline en el router → `models/` (SQLAlchemy) → PostgreSQL. Los `schemas/` (Pydantic) validan entrada/salida en cada endpoint. `_helpers.py` centraliza el patrón de autorización: `_accessible_diagram_filter(me)` filtra diagramas donde el usuario es dueño o colaborador, usado por casi todos los routers para no duplicar esa lógica.

### Routers y endpoints principales (`backend/app/routers/`)

| Router | Prefix | Endpoints |
|---|---|---|
| `auth.py` | `/auth` | `POST /auth/sign-in` (único endpoint de auth activo) |
| `diagramas.py` | `/diagrams` | `POST /diagrams`, `GET /diagrams`, `GET /diagrams/{id}`, `DELETE /diagrams/{id}`, `GET /diagrams/{id}/full`, `GET/POST /diagrams/{id}/collaborators`, `DELETE /diagrams/{id}/collaborators/{user_id}` |
| `classes.py` | `/diagrams` | `POST /diagrams/{id}/classes`, `GET /diagrams/classes/{class_id}`, `GET /diagrams/{id}/classes`, `PATCH /diagrams/classes/{class_id}`, `DELETE /diagrams/classes/{class_id}` |
| `atributos.py` | `/diagrams` | `GET/POST /diagrams/classes/{class_id}/attributes`, `PATCH/DELETE /diagrams/attributes/{attr_id}` |
| `metodo.py` | `/diagrams` | mismo patrón que atributos, para `methods` |
| `relacion.py` | `/diagrams` | `POST /diagrams/{id}/relations`, `GET /diagrams/{id}/relations`, `PATCH/DELETE/GET /diagrams/relations/{relation_id}` |
| `export.py` | `/diagrams` | `POST /diagrams/{id}/export-download` (dispara el pipeline de `exporters/`, ver sección 9) |
| `ai.py` | `/diagrams` | `POST /diagrams/{id}/ai/command` (asíncrono, `202 Accepted`, usa `BackgroundTasks`). Desde la Fase 2 registra la consulta en el chat del diagrama (es pública) y devuelve `request_id` |
| `chat.py` | `/diagrams` | `GET /diagrams/{id}/chat?limit=&before_seq=` (historial), `POST /diagrams/{id}/chat` `{text, ask_ai}` (Fase 2: chat grupal + consultas a la IA con `@IA`) |
| `xmi.py` | `/diagrams` | `GET /diagrams/{id}/export-xmi`, `POST /diagrams/{id}/import-xmi` |
| `vision.py` | `/vision` | `POST /vision/detect` (sube foto, Gemini transcribe, no crea nada), `POST /vision/apply` (crea el diagrama con lo ya revisado por el usuario) |
| `realtime.py` | `/diagrams` | `WS /diagrams/{id}/ws` (WebSocket, ver protocolo abajo) |

`GET /health` y `GET /` están definidos directo en `main.py`, no en un router.

**No existe** endpoint de registro de usuarios (`sign-up`) activo, aunque el schema `SignUpIn` existe en `schemas/auth.py` — no está conectado a ninguna ruta.

### WebSocket (`WS /diagrams/{diagram_id}/ws`)
Autenticación por query string (`?token=...`, no por header, porque el WebSocket nativo del navegador no permite headers custom). Protocolo (documentado en el docstring de `realtime.py`):
- El cliente puede mandar: `{"action": "lock"|"unlock", "class_id": "..."}` (exclusión mutua por clase) y `{"action": "cursor", "x", "y", "label"}` / `{"action": "cursor_left"}` (cursores en vivo).
- El servidor emite: `connected`, `locks.snapshot`, `class.locked`, `class.unlocked`, `lock.denied`, `cursor.move`, `cursor.left`, y desde la Fase 2: `presence` (lista de usuarios conectados, sin repetir pestañas), `chat.message` (mensaje nuevo del chat, de un colaborador o de la IA) y `ai.started`/`ai.done`/`ai.error` con `request_id` + `requested_by` (quién preguntó).
- Cada conexión tiene un `conn_id` propio (no el email) para distinguir pestañas del mismo usuario.
- El color de cada cursor se calcula por checksum del email (no `hash()`, que varía entre reinicios del proceso), sobre una paleta fija de 8 colores.

### Entidades / modelos (`backend/app/models/`)
Ver tablas detalladas en la sección 8 (Base de datos).

### Autenticación y autorización (`backend/app/core/security.py`)
- Contraseñas con `bcrypt` (truncadas a 72 caracteres, límite del algoritmo).
- JWT firmado con `JWT_SECRET`/`JWT_ALG`, claims `sub` (email), `kind="access"`, `iat`, `exp`.
- Dependencia `get_current_user`: exige `Authorization: Bearer <token>`, valida `kind == "access"`, busca el usuario por email y verifica `active`.
- **No hay lógica de refresh token implementada**, pese a que `REFRESH_EXPIRE_DAYS` está definido en `config.py`.
- Autorización a nivel de recurso: cada router usa `_accessible_diagram_filter` (dueño o colaborador) antes de permitir leer/editar.

### Reglas de negocio importantes
- El asistente de IA (texto) nunca genera un diagrama completo desde una descripción de negocio — solo ejecuta ediciones puntuales, con un contrato fijo de "tools" compartido conceptualmente con el asistente local de la app móvil.
- La detección desde foto (`/vision/detect`) nunca aplica cambios directo a un diagrama: siempre devuelve una vista previa para que el usuario la revise y corrija antes de confirmar (`/vision/apply`).
- La exclusión mutua (locks) es a nivel de clase individual, no de diagrama completo: dos personas pueden editar clases distintas del mismo diagrama a la vez, pero no la misma clase.

## 6. Frontend

### Arquitectura
React con Vite. Estado por feature vía hooks custom (`useClassesAndDetails`, `useRelations`, `useDiagramLocks`, `useLiveCursors`, etc.), cada uno encapsulando su propia lógica de fetch + WebSocket + optimistic update + undo. Estado de sesión global con `zustand` (`store/auth.js`).

### Rutas (`src/App.jsx` + `src/main.jsx`)
`main.jsx` envuelve la app en `<BrowserRouter>`. Rutas definidas en `App.jsx`:
- `/login` → `LoginPage` (pública)
- `/` → `HomePage`, lista de diagramas (protegida)
- `/diagram/:id` → `Diagram`, el editor (protegida)
- `*` → redirect a `/`

Las rutas protegidas usan un wrapper que lee `useAuth(s => s.token)` y redirige a `/login` si no hay sesión.

### Componentes principales (`src/components/`)
- `canvas/`: el lienzo del editor — `Sheet.jsx` (contenedor), `ClassCard/` (tarjeta de clase, con subcomponentes Header/Body/Ports), `ConnectionLayer.jsx` (dibuja las relaciones en SVG).
- `panels/`: `Inspector.jsx` (edición de clase seleccionada), `RelationInspector.jsx` (edición de relación seleccionada), `AiAssistantPanel.jsx`, `ImportFromPhotoModal.jsx`, `CollaboratorsModal.jsx`, `AssociationClassModal.jsx` (conversión a clase de asociación UML 2.5).
- `layout/`: `HeaderBar.jsx`, `LeftPanel.jsx`.
- `common/`: `Icon.jsx`, `ApiStatusBadge.jsx`, `HelpGuide.jsx`.

### Servicios / API (`src/api/`)
Un archivo por recurso: `classes.js`, `relations.js`, `diagrams.js`, `ai.js`, `vision.js`, `xmi.js`, `export.js`, `realtime.js`. Todos consumen `api/client.js`.

### Modelos/interfaces
No hay TypeScript ni interfaces formales — los datos se mapean con funciones helper por archivo (ej. `mapClass()` en `api/classes.js`) porque el backend a veces devuelve nombres de campo en español (`origen_id`, `tipo`) directo del ORM y otras veces en inglés según el endpoint.

### Manejo de autenticación
`store/auth.js` (zustand): guarda el token en memoria y lo persiste manualmente en `localStorage` (`uml_access_token`, `uml_email`), decodificando el JWT con `jwt-decode` para extraer el email al cargar.

### Comunicación con el backend
`api/client.js`: instancia de `axios` con `baseURL` = `VITE_API_URL` (normalmente `/api`, proxeado por nginx) y `timeout: 10000` global (algunos endpoints lentos, como `/vision/detect`, pasan un `timeout` más largo por request). Interceptor de request adjunta `Authorization: Bearer`; interceptor de response desloguea automáticamente en un `401`.

## 7. Mobile

### Estado real (importante)
- **Nunca se compiló.** No existe `mobile/android/`, no existe `mobile/ios/`, no hay `pubspec.lock`, no hay carpeta `build/`.
- `mobile/README.md` documenta explícitamente los pasos pendientes: instalar Java 17 + Android SDK + Flutter, correr `flutter create --platforms=android` para generar la carpeta `android/`, ajustar permisos de micrófono y `minSdk=24`, y recién ahí poder compilar.
- Todo `mobile/` está sin trackear en git (`git status` lo muestra como untracked completo).

### Arquitectura (según el código escrito, sin verificar en ejecución)
14 archivos `.dart` en `mobile/lib/`. Estado global con `ChangeNotifier` (`app_state.dart`), sin un framework de estado más complejo.

### Pantallas (`mobile/lib/screens/`)
`login_screen.dart`, `diagram_list_screen.dart`, `diagram_screen.dart` (vista simplificada del diagrama: lista de tarjetas, sin lienzo de posición libre ni cursores en vivo — decisión explícita para simplificar la versión móvil), `assistant_screen.dart` (asistente por voz/texto).

### Servicios (`mobile/lib/services/`)
- `api_client.dart`: cliente HTTP contra el **mismo backend FastAPI** que usa la web.
- `auth_service.dart`: guarda el JWT en `SharedPreferences`.
- `realtime_service.dart`: cliente WebSocket, mismo protocolo que `backend/app/routers/realtime.py`.
- `local_llm_service.dart`: asistente de IA **100% offline**, modelo Qwen2.5-1.5B-Instruct cuantizado (GGUF Q4_K_M) corriendo con `llamadart` (bindings de llama.cpp), mismo contrato de "tools" que el asistente web.
- `speech_service.dart`: reconocimiento de voz offline con Vosk (`vosk_flutter_2`).
- `model_downloader.dart`: los modelos de IA (~1GB el LLM, ~50MB Vosk) no van empaquetados en el APK — se descargan la primera vez que se abre el asistente.

### Modelos (`mobile/lib/models/diagram.dart`)
Espejo de los schemas Pydantic del backend (clases, atributos, métodos, relaciones), con `fromJson` tolerantes a nombres en español o inglés según el endpoint.

### Navegación
No se confirmó un sistema de rutas nombradas — la navegación entre pantallas usa `Navigator` estándar de Flutter (push/pop directo entre widgets), a juzgar por la estructura de `screens/`.

### Comunicación con el backend
REST vía `api_client.dart` + WebSocket vía `realtime_service.dart`, ambos apuntando a la URL configurada en `mobile/lib/config.dart` (default `http://10.0.2.2:8000`, la dirección especial del emulador Android hacia el `localhost` de la PC).

## 8. Base de datos

**Motor**: PostgreSQL 16.

**Tablas** (SQLAlchemy, `backend/app/models/`):

| Tabla | Columnas principales | Relaciones |
|---|---|---|
| `user` | `id` (PK int), `email`, `name`, `password_hash`, `role` (enum: admin/editor/viewer), `active`, `created_at`, `updated_at` | — |
| `diagram` | `id` (PK UUID), `title`, `owner_id` (FK → user.id), `updated_at` | dueño de N clases, N relaciones, N colaboradores |
| `diagram_collaborator` | `id` (PK UUID), `diagram_id` (FK), `user_id` (FK), `role` (enum: EDITOR/VIEWER), `created_at` | único por (diagram_id, user_id) |
| `clase` | `id` (PK UUID), `nombre`, `diagram_id` (FK), `x_grid`, `y_grid`, `w_grid`, `h_grid`, `z_index` | N atributos, N métodos, origen/destino de relaciones |
| `relacion` | `id` (PK UUID), `diagram_id` (FK), `origen_id`/`destino_id` (FK → clase.id), `tipo` (enum: ASSOCIATION/AGGREGATION/COMPOSITION/INHERITANCE/DEPENDENCY), `etiqueta`, anclajes visuales (`src_anchor`, `dst_anchor`, offsets, lanes), multiplicidad (`mult_origen_min/max`, `mult_destino_min/max`) | — |
| `atributo` | `id` (PK UUID), `nombre`, `tipo` (string libre, default "string"), `requerido` (bool), `clase_id` (FK) | único por (clase_id, nombre) |
| `metodo` | `id` (PK UUID), `nombre`, `tipo_retorno` (default "void"), `clase_id` (FK) | único por (clase_id, nombre) |
| `chat_message` (Fase 2) | `id` (PK UUID), `diagram_id` (FK), `role` (enum: USER/ASSISTANT/ERROR), `author_id` (FK user, NULL para la IA), `author_name`, `author_email`, `content`, `asks_ai`, `reply_to_id` (FK chat_message), `addressed_to_id`/`addressed_to_name` (a quién responde la IA), `actions` (JSONB), `created_at`, `seq` (identity, orden total) | N por diagrama |

**Migraciones** (`backend/alembic/versions/`, 3 archivos en orden):
1. `a112c4d14f5b_init_schema.py` — esquema inicial (crea todas las tablas base excepto `diagram_collaborator`).
2. `cd269a313b01_add_unique_constraint_on_attribute_and_.py` — agrega constraints únicos `uq_atributo_clase_nombre` (clase_id, nombre) y `uq_metodo_clase_nombre` (clase_id, nombre); el `downgrade()` los elimina, como es estándar.
3. `3f9f653ec7cc_add_diagram_collaborators.py` — crea la tabla `diagram_collaborator`.
4. `8a1c2e4f6b90_add_es_clase_asociacion_to_relacion.py` — agrega `relacion.es_clase_asociacion`.
5. `b7d3f1a2c9e4_add_chat_message.py` — (Fase 2) crea la tabla `chat_message`.

**Nombre de la base** (diagramador): `parcial_sw` (default de `POSTGRES_DB` en `docker-compose.yml`, configurable por variable de entorno `DB_NAME`).

## 9. Integración

**Flujo principal (edición manual de un diagrama):**
```
Usuario → frontend (React) → PATCH/POST /diagrams/... → backend → PostgreSQL
                                                              │
                                                              ▼
                                            WebSocket: broadcast del cambio
                                            a todos los demás conectados
                                            al mismo diagrama
```

**Flujo de generación de backend Spring Boot** (`export.py` + `exporters/`):
1. `POST /diagrams/{id}/export-download` arma un dict con clases/atributos/relaciones desde el ORM.
2. `uml_to_json.export_diagram_to_json`: **normaliza** todos los nombres de clase y atributo a identificadores Java válidos (sin espacios ni símbolos, PascalCase para clases, camelCase para atributos) y valida el diagrama (`validator.py`).
3. `project_builder.build_project` ejecuta el pipeline completo:
   - `json_to_full_orm.generate_from_json` → modelos JPA (`@Entity`).
   - `model_to_repository.generate_repositories` → interfaces `JpaRepository`.
   - `repository_to_service.generate_services` → clases de servicio.
   - `service_to_controller.generate_controllers` → controladores REST CRUD.
   - `model_to_dto.generate_dtos` → DTOs.
   - `postman_generator.generate_postman` → colección Postman (una carpeta por clase + Health check).
   - Archivos fijos renderizados desde templates Jinja2: `pom.xml`, `application.properties`, `DemoApplication.java`, `HealthController.java`, `Dockerfile`, `docker-compose.yml`, `README.md`.
4. Todo se comprime en un ZIP y se devuelve como descarga.

**Flujo de asistente de IA (texto, web)**: `POST /diagrams/{id}/ai/command` → encolado con `BackgroundTasks` → llama a Gemini con el contrato de "tools" → aplica la tool elegida sobre la base → notifica el cambio por WebSocket.

**Flujo de chat grupal y consultas a la IA (Fase 2, CU-14/15/16)**: `POST /diagrams/{id}/chat` guarda el mensaje y lo difunde como `chat.message` a todos los conectados. Si el texto contiene `@IA` (o `ask_ai=true`), además `chat_service.run_ai_question_background` llama al modelo indicándole **quién pregunta** (nombre + email) y el historial de consultas previas de **ese mismo usuario** en el diagrama; la respuesta se guarda dirigida a esa persona (`addressed_to_*`, `reply_to_id`) y se difunde a todos. Si el modelo no nombra a quien preguntó, `chat_service.address_reply` antepone su nombre. En el frontend, `ChatPanel.jsx` (+ `hooks/useTeamChat.js`) reemplaza al antiguo panel privado del asistente.

**Flujo de importar foto**: `POST /vision/detect` (sube imagen, Gemini Vision la transcribe a JSON, no se guarda nada aún) → usuario revisa/corrige en el frontend → `POST /vision/apply` (crea el diagrama real con lo confirmado).

## 10. Funcionalidades implementadas

Confirmado funcionando (probado en esta sesión con Docker real, no solo revisión de código):
- CRUD completo de diagramas, clases, atributos, métodos, relaciones.
- Colaboración en tiempo real vía WebSocket: cambios, exclusión mutua por clase, cursores en vivo con nombre y color estables.
- Login con JWT.
- Asistente de IA por texto (Gemini) para ediciones puntuales del diagrama.
- Importar diagrama desde una foto (Gemini Vision), con vista previa editable antes de confirmar.
- Exportar/importar diagrama en formato XMI 2.1 (compatible con Enterprise Architect, vía `Publish → Import/Export Package from XMI` en EA).
- **Generación de backend Spring Boot completo**, verificado de punta a punta: compila con Maven, levanta con `docker compose up`, Hibernate crea las tablas, responde CRUD real vía REST.
- Conversión de relación muchos-a-muchos en "clase de asociación" explícita (UML 2.5): crea una clase intermedia visible con sus FKs, en vez de depender solo de la tabla `@JoinTable` invisible que genera Hibernate.
- Docker Compose para el diagramador completo (backend + frontend + Postgres) y, por separado, para cada backend Spring Boot exportado (con puertos distintos para poder correr ambos a la vez).

## 11. Funcionalidades en desarrollo

- **App móvil Flutter**: todo el código está escrito (14 archivos `.dart`), pero nunca se compiló ni se corrió. Falta: instalar Android SDK y generar la carpeta `android/` (`flutter create`), correr `flutter pub get`, y probar en un dispositivo real. La API exacta del método `generate()` del paquete `llamadart` no está confirmada al 100% contra el código real (puede necesitar ajustes al compilar por primera vez, según nota dejada en el propio código).
- El `docker-compose.yml` de la raíz del proyecto (diagramador) todavía no está commiteado a git (aparece como untracked).

## 12. Decisiones importantes (no cambiar sin razón clara)

- **El nombre de campo en las respuestas del backend es inconsistente entre endpoints a propósito conocido, no por error**: algunos devuelven español directo del ORM (`origen_id`, `tipo`, `mult_origen_max`) y otros usan alias en inglés (`from_class`, `type`). El frontend ya maneja ambos casos con `??` en varios lugares. Si se toca esto, hay que revisar TODOS los consumidores (frontend web y, eventualmente, mobile).
- **Los nombres de clase/atributo se normalizan a identificadores Java válidos únicamente en el pipeline de exportación** (`uml_to_json._normalize_diagram`), nunca en la base de datos ni en el diagrama que ve el usuario en el editor. El diagrama guardado conserva los nombres originales (con espacios, tildes, lo que sea) tal cual los escribió el usuario o los leyó Gemini de una foto.
- **Puertos fijos y separados entre el diagramador y cualquier backend Spring Boot exportado**, a propósito para poder correr ambos Docker Compose a la vez sin conflicto: diagramador en 5433/8000/5173, backend exportado en 5434/8090.
- **El asistente de IA (tanto web como el diseño previsto para mobile) nunca genera un diagrama completo desde una descripción de negocio.** Es una restricción explícita de la cátedra: solo ejecuta ediciones puntuales que el usuario ya pidió.
- **La detección de foto nunca aplica cambios directo**: siempre hay un paso de revisión humana (`/vision/detect` → frontend → `/vision/apply`) antes de tocar la base de datos.
- **El timeout de Axios para `/vision/detect` es más largo (90s) que el default global (10s) a propósito**, porque el backend reintenta contra Gemini con backoff y puede tardar más que el default. El timeout de proxy de nginx (100s) es a su vez mayor que el de Axios, también a propósito, para que nginx nunca corte una respuesta que el backend está por mandar.

## 13. Problemas conocidos

- **No hay endpoint de registro de usuarios activo** (`sign-up`), pese a que el schema existe. Los usuarios deben crearse por otro medio (seed, acceso directo a la base, o un endpoint no confirmado en este audit).
- **No hay refresh token implementado**, pese a que `REFRESH_EXPIRE_DAYS` está en la configuración. La sesión expira cuando expira el access token (`ACCESS_EXPIRE_MIN`, default 480 minutos) y el usuario debe volver a loguearse.
- **Inconsistencia de nombres de campo español/inglés entre endpoints** (ver sección 12) — no es un bug per se, pero es una fuente real de errores si se agrega código nuevo sin verificar el shape exacto de cada endpoint primero.
- **App móvil sin compilar**: no se puede afirmar que el código Dart funcione hasta que se compile por primera vez. La integración con `llamadart` en particular tiene riesgo de necesitar ajustes.
- **Mobile no está commiteado a git** — cualquier trabajo ahí corre riesgo de perderse si no se agrega al repo.

## 14. Reglas para futuras sesiones

- No inventar elementos que no existan (endpoints, tablas, archivos, funcionalidades). Si no se puede confirmar algo con el código, decirlo explícitamente.
- Revisar el código antes de afirmar que algo existe — este documento puede quedar desactualizado si el código cambia después de escribirlo.
- Mantener compatibilidad entre frontend, backend, mobile y base de datos: un cambio de contrato en un endpoint usado por frontend Y mobile rompe ambos si no se actualizan los dos.
- No modificar contratos de API (shape de request/response) sin revisar todos sus consumidores reales (buscar el endpoint en `frontend/src/api/` y en `mobile/lib/services/`).
- No cambiar la base de datos (modelos, migraciones) sin revisar el impacto en backend (schemas), frontend (mapeo de campos) y mobile (modelos Dart) cuando corresponda.
- Mantener esta documentación y el código sincronizados: si se hace un cambio estructural relevante, actualizar este archivo.
- Antes de reconstruir contenedores Docker para probar un cambio, verificar qué contenedores están corriendo y en qué puertos (`docker ps`), para no chocar con el backend Spring Boot exportado si también está corriendo.

## 15. Estado actual

Al momento de escribir este documento:
- El diagramador (backend + frontend + Postgres) corre en Docker y fue verificado funcionando de punta a punta: login, CRUD de diagramas/clases/relaciones, colaboración en tiempo real, asistente de IA, importar foto, exportar/importar XMI.
- El generador de backend Spring Boot fue verificado de punta a punta con un caso real (diagrama de 7 clases importado desde una foto): compila con Maven, levanta con Docker, Hibernate crea las tablas, responde CRUD real.
- Se hizo una limpieza de código muerto en backend, frontend y exporters (archivos completos sin uso y bloques de código comentado), verificando después de cada cambio que backend y frontend siguieran reconstruyendo y respondiendo bien en Docker.
- La app móvil Flutter tiene todo su código fuente escrito pero nunca se compiló. El usuario instaló Flutter recién en esta sesión (confirmado en el PATH de Windows); todavía falta generar la carpeta `android/` y compilar por primera vez.
- Working tree con cambios sin commitear (ver lista completa en el reporte de auditoría de esta sesión, o correr `git status`): principalmente los archivos tocados durante la limpieza de código muerto, y todo `mobile/`, que nunca se agregó a git.

## 16. Próximos pasos

En orden lógico sugerido:
1. Compilar la app móvil por primera vez: generar `mobile/android/` con `flutter create --platforms=android`, correr `flutter pub get`, resolver cualquier error de compilación que surja (especialmente en la integración con `llamadart`, marcada como no confirmada al 100%).
2. Probar la app móvil en un dispositivo físico real, incluyendo la descarga de los modelos de IA (LLM + Vosk) la primera vez que se abre el asistente.
3. Confirmar si hace falta un endpoint de registro de usuarios para el examen, o si los usuarios se crean siempre por otro medio (seed/acceso directo a la base).
4. Decidir si conviene implementar refresh token o si el tiempo de expiración actual (8 horas) es suficiente para el examen.
5. Commitear a git el `docker-compose.yml` de la raíz y todo `mobile/`, que hoy están sin trackear.
