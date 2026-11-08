# Contexto mobile — parcial_sw

## Qué es (objetivo real, confirmado con el usuario)

`mobile/` **no es** una app para diseñar diagramas UML — eso se hace desde
la web (`frontend/`). Es un **cliente genérico del protocolo UAP**: se
conecta a cualquier backend Spring Boot generado por el diagramador ese
mismo día (dominio arbitrario — hoy verificado contra un backend bancario
con Bank/Customer/ATM/Account/etc, pero podría ser cualquier otra cosa) y
lo opera por voz o texto con un asistente conversacional, sin que nadie
tenga que programarle una interfaz visual específica a cada dominio.

La UI para el backend generado (formularios, listas, pantallas propias del
dominio bancario/veterinaria/lo-que-sea) **se construye el día del examen**,
no ahora — confirmado explícitamente por el usuario. El foco actual es el
asistente (chat/voz) genérico.

## Estado real de compilación (verificado, corriendo en un dispositivo físico)

Ya **no** es cierto que "nunca se compiló" (como decía una versión previa
de este documento). Verificado en esta sesión:

- `mobile/android/` generado y trackeado en git.
- `flutter build apk --debug` compila sin errores.
- El APK se instaló y corrió en un teléfono físico real (Redmi/Xiaomi,
  Snapdragon 662, Android 15/AQ3A).
- Conexión real contra un backend Spring Boot generado, levantado con
  Docker a partir de un ZIP exportado del diagramador — `curl` y la app
  confirmaron respuestas reales de `/uap/v1/manifest` y `/uap/v1/tools`.

## Arquitectura

Dart puro en `mobile/lib/`, estado global con `ChangeNotifier`
(`app_state.dart`, vía `provider`). Estructura por área:

```
lib/
  uap/       cliente + parser + coerción + descubrimiento + reconexión
  db/        SQLite offline-first (local_records/sync_outbox/etc)
  voice/     texto a voz nativo (flutter_tts)
  services/  LLM local, reconocimiento de voz (Vosk), API/Auth del
             diagramador (código legado, ya no en el camino de navegación)
  screens/   pantallas
```

## Flujo de navegación (main.dart)

`main.dart` → `_Bootstrapper` (carga sesión/TTS) → **`UapConnectScreen`**
directo. No hay login ni selector de modo en el camino: el flujo del
diagramador (`login_screen.dart`, `diagram_list_screen.dart`,
`diagram_screen.dart`, `mode_selector_screen.dart`, `assistant_screen.dart`,
`ApiClient`, `AuthService`) sigue existiendo en el código pero **no se usa**
desde la navegación real de la app. Se dejó así a propósito (decisión
explícita del usuario) por si hace falta después, sin borrarlo.

## Pantallas activas (`mobile/lib/screens/`)

- **`uap_connect_screen.dart`**: primera pantalla real de la app. Elegir
  modo de conexión (USB vía `adb reverse`, o WiFi/LAN) y descubrir el
  contrato UAP del backend (`AppState.connectToUap`). Si falla, muestra el
  error tal cual (no un mensaje genérico).
- **`historial_screen.dart`**: modo "Historial" — chat con texto, sin
  micrófono. Carga el LLM local al entrar (con indicador de progreso).
  Muestra un banner de estado de conexión reactivo (`ListenableBuilder`
  sobre `ConnectionManager`, no vía `context.watch<AppState>()` — el
  `ConnectionManager` es su propio `ChangeNotifier` separado).
- **`alexa_screen.dart`**: modo "Alexa" — solo botón de mic grande, sin
  campo de texto. Carga Vosk (STT) y el LLM al entrar. Lee las respuestas
  con `flutter_tts`, avisando si no hay voz en español instalada.

Ambas pantallas comparten el mismo pipeline: texto del usuario → LLM local
(`resolveUapCommand`) → `IntentParser.parse()` (autoridad real) → si es
`ParsedInvocation`, se invoca contra el backend; si es `Conversational`
(charla casual) o `ChatReply` (el LLM decidió que es charla libre), se
responde directo sin tocar el backend.

## `lib/uap/` — el núcleo del cliente genérico

- **`uap_config.dart` / `UapEndpoint`**: URL efectiva y headers según modo
  de conexión (USB manda `Host` explícito, WiFi/LAN no).
- **`uap_client.dart`**: cliente HTTP contra `/uap/v1/*`. Todas las
  llamadras tienen **timeout de 10s** (agregado tras detectar que su
  ausencia dejaba `ConnectionManager` pegado en "sincronizando" para
  siempre si la conexión se colgaba).
- **`uap_manifest.dart`**: modelos del contrato descubierto (`UapContract`,
  `UapEntity`, `UapTool`), indexado por alias/toolId.
- **`type_coercion.dart`**: función pura, convierte valores crudos al tipo
  declarado por el schema (booleanos en español, números con separadores
  latinos, fechas).
- **`intent_parser.dart`**: el parser determinista, autoridad real sobre
  qué se ejecuta. El LLM nunca decide directo. Pipeline: detectar charla
  casual (saludo/gracias/ayuda/despedida, vía regex, solo si no hay una
  aclaración pendiente) → resolver entidad (alias, singular/plural,
  tolerancia a typos) → resolver verbo → validar tool contra el contrato →
  validar/sanitizar campos → coercionar tipos → verificar requeridos.
  Devuelve uno de: `ParsedInvocation`, `NeedsClarification`,
  `Conversational`, `Rejected`.
  - **`ConversationContext`**: memoria de UN turno (no una sesión entera).
    Cuando el parser pide una aclaración ("¿qué querés hacer con
    productos?"), devuelve junto con la pregunta qué entidad/verbo/campos
    ya se resolvieron; la pantalla se lo pasa de vuelta en el próximo
    `parse()`. Sin esto, responder solo "crear" a esa pregunta fallaba
    porque el mensaje aislado no tenía ninguna entidad en su propio texto.
- **`response_phrasing.dart`**: JSON del backend → frase natural en
  español. Nunca se muestra JSON crudo como respuesta principal.
- **`connection_manager.dart`**: orquesta sincronización — conectividad,
  ciclo de vida de la app, single-flight, backoff `[1,2,5,10,30]`s.

## `lib/db/` — offline-first

`uap_database.dart` (SQLite vía `sqflite`, 4 tablas: `local_records`,
`sync_outbox`, `sync_metadata`, `identity_map`) + `local_repository.dart`
(CRUD local, reconciliación de IDs sin duplicados, idempotencia).

## `lib/services/local_llm_service.dart` — LLM local

Modelo: **Gemma 3 1B IT, GGUF Q4_K_M**, empaquetado en
`assets/models/assistant.gguf` (dentro del APK, no se descarga). Corre con
`llamadart` (bindings de llama.cpp).

- **`resolveCommand()`**: contrato original del diagramador (9 tools
  fijas). Intacto, no se toca.
- **`resolveUapCommand()`**: contrato genérico UAP. El LLM puede responder
  de dos formas en un solo prompt/llamada: `{"tool":...,"args":...}`
  (propuesta de operación, el parser la valida) o `{"chat":"..."}`
  (charla libre, se muestra tal cual). Se decidió no hacer una segunda
  llamada al LLM para "clasificar intención primero" por costo de latencia
  en un chip sin GPU.
- `extractFirstJsonObject`/`parseLlmResponseFromRaw`: parseo tolerante a
  texto extra alrededor del JSON (el modelo a veces agrega explicación
  pese a la instrucción).

### Bug real encontrado y arreglado: SIGILL al cargar cualquier modelo

`llamadart 0.5.4` (fijado originalmente por un conflicto de dependencia
con `vosk_flutter_2`) crashea con `SIGILL` en `llama_model_load_from_file`
en **cualquier** chip ARM sin soporte `i8mm`/`dotprod` — confirmado con
logcat real contra un Snapdragon 662 (`Features: fp asimd evtstrm aes
pmull sha1 sha2 crc32`, sin `dotprod`/`i8mm`/`asimddp`). Es un bug conocido
del proyecto (`leehack/llamadart#95`, mismo síntoma reportado en un Exynos
1380 y un Snapdragon 680), arreglado upstream en `llamadart 0.6.9` con
selección automática de variante de CPU en runtime.

Se actualizó a `llamadart ^0.6.9` y se forzó `archive ^4.0.7` vía
`dependency_overrides` (verificado que la API real que usa
`vosk_flutter_2` — `ZipDecoder().decodeBytes()`/`extractArchiveToDisk()` —
es estable entre `archive` 3.x y 4.x).

## `lib/services/model_downloader.dart`

`ensureLlmModel()` copia el `.gguf` desde `assets/models/assistant.gguf`
(bundle del APK) al almacenamiento privado de la app en el primer
arranque — **no** descarga nada por HTTP para el LLM (a diferencia del
diseño original con Qwen, que sí se descargaba). `downloadVosk()` sigue
igual: el modelo de voz español (~50MB) se descarga en runtime, no
justifica inflar el APK.

El archivo `.gguf` en sí (~1GB) **no se versiona en git** — hay que
descargarlo aparte antes de compilar (ver `mobile/README.md`, sección
"Modelo local (Gemma 3 1B)").

## `lib/voice/tts_service.dart`

Texto a voz nativo de Android (`flutter_tts`), offline, usa las voces ya
instaladas en el sistema. Detecta si hay una voz en español disponible y
avisa en la UI si no la hay, en vez de quedar mudo sin explicación.

## Servicios legados del diagramador (no tocados, no usados en el flujo activo)

`api_client.dart`, `auth_service.dart`, `realtime_service.dart`,
`models/diagram.dart` — cliente REST/WebSocket contra el backend FastAPI
del diagramador. Siguen compilando y funcionando, pero `main.dart` ya no
navega hacia ellos.

## Permisos y configuración Android

`AndroidManifest.xml`: `INTERNET`, `RECORD_AUDIO`, `ACCESS_NETWORK_STATE`,
`android:usesCleartextTraffic="true"` (el backend generado es HTTP plano
en LAN). `build.gradle.kts`: `minSdk = 24` (requerido por
`llamadart`/`vosk_flutter_2`, antes usaba el default de Flutter).

## Verificado end-to-end en esta sesión

1. Pipeline `exporters/` genera un backend Spring Boot con protocolo UAP
   real (probado contra un export bancario real: Bank, Customer, ATM,
   Account, ATMTransactions, CurrentAccount, SavingAccount).
2. Ese backend compila con Maven y corre en Docker (`docker compose up`),
   expone `/uap/v1/manifest`, `/uap/v1/tools`, etc. con datos reales.
3. La app móvil se conecta por USB (`adb reverse`) contra ese backend real.
4. El parser determinista resuelve pedidos en español, incluida charla
   casual y conversaciones de varios turnos.
5. El LLM local (Gemma 3 1B) carga y genera texto en un dispositivo físico
   de gama baja (lento — sin GPU, ~1GB de modelo — pero funciona).

## Pendiente de verificar / limitaciones conocidas

- **Rendimiento del LLM**: funciona pero es notablemente lento en un
  Snapdragon 662 sin GPU. Si resulta impracticable para el examen, queda
  la alternativa de volver a Qwen2.5-1.5B (ya probado antes) para comparar.
- El pluralizador (`"atmtransactions"` → `"atmtransactionss"`, doble "s")
  en `exporters/generators/uap_generator.py` es simplista — bug menor
  detectado en pruebas reales, no bloqueante, no arreglado todavía.
- La UI específica del dominio del backend generado (pantallas propias
  para Bank/Customer/etc, más allá del chat genérico) es trabajo del día
  del examen, no de esta etapa.
- No se probó el modo offline real (crear/editar sin conexión y
  sincronizar después) contra un dispositivo físico, solo con SQLite en
  el test runner de escritorio (`sqflite_common_ffi`).
