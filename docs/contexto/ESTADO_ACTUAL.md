# Estado actual — parcial_sw

**Fecha de actualización**: 2026-09-22.

## Resumen del proyecto (5 piezas)

1. **Diagramador** (backend FastAPI + frontend React): editor colaborativo
   de diagramas UML, terminado y funcional, **no tocado** en esta etapa de
   trabajo.
2. **`exporters/`**: genera un backend Spring Boot completo a partir de un
   diagrama, incluyendo el protocolo **UAP** (manifest/schema/tools/
   invoke/sync) — verificado end-to-end contra un export real (compiló con
   Maven, corrió en Docker, respondió peticiones reales).
3. **`mobile/`**: cliente genérico de UAP con asistente conversacional (voz
   o texto), LLM local (Gemma 3 1B), SQLite offline-first — verificado
   corriendo en un teléfono físico real, conectado a un backend generado.
4. **Backend Spring Boot generados**: artefacto de salida de `exporters/`,
   no forma parte del repo en sí.
5. **UI específica del backend generado**: pendiente, se construye el día
   del examen según el dominio real del diagrama que se dibuje.

## Trabajo reciente (esta sesión)

### `exporters/` — protocolo UAP genérico

Nuevo generador `exporters/generators/uap_generator.py` + 9 templates
Java (`UapManifestController`, `UapSchemaController`, `UapToolsController`,
`UapToolDispatcher`, `UapSyncController`, `UapGeneration`, `UapChangeLog`,
`UapCoerce`, `JacksonTimeZoneConfig`), integrados en el pipeline existente
(`project_builder.py`). Sin reflexión Java (dispatcher generado como
switch estático en build-time). 77 tests de Python pasando.

**Verificado real, no solo por tests**: se descargó un ZIP exportado real
(dominio bancario: Bank/Customer/ATM/Account/etc), se levantó con
`docker compose up --build`, compiló con Maven, y respondió correctamente
a `curl` contra `/uap/v1/manifest` y `/uap/v1/tools` con datos reales.

### `mobile/` — cliente UAP, LLM local, asistente conversacional

Ver `CONTEXTO_MOBILE.md` para el detalle completo. Resumen de lo hecho en
esta sesión, en orden:

1. Diseño e implementación completa del cliente UAP genérico (`lib/uap/`),
   SQLite offline-first (`lib/db/`), TTS (`lib/voice/`), pantallas nuevas.
2. **Corregido un malentendido de una sesión anterior**: la app ofrecía
   "Diseñar diagramas" como opción principal, cuando el mobile no es para
   eso (eso se hace en la web). Se cambió `main.dart` para ir directo a
   `UapConnectScreen`, dejando el código del diagramador sin tocar pero
   fuera del camino de navegación.
3. **Bug real encontrado y arreglado**: `llamadart 0.5.4` crasheaba con
   `SIGILL` al cargar CUALQUIER modelo GGUF en el teléfono de prueba
   (Snapdragon 662, sin soporte `i8mm`/`dotprod`) — confirmado con logcat
   real. Bug conocido upstream (`leehack/llamadart#95`), arreglado en
   `0.6.9`. Se actualizó la dependencia con un `dependency_overrides` para
   `archive` (verificado que no rompe `vosk_flutter_2`).
4. **Bug real**: `UapClient` no tenía timeout en sus requests HTTP — una
   conexión colgada dejaba la UI pegada en "sincronizando" para siempre.
   Arreglado con timeout de 10s.
5. **Bug real**: ni `HistorialScreen` ni `AlexaScreen` cargaban el LLM/Vosk
   antes de usarlos — el botón de mic tiraba "Bad state" al tocarlo.
   Arreglado con una etapa de preparación explícita en cada pantalla.
6. **Bug real**: el banner de estado de conexión no se actualizaba en
   vivo (el `ConnectionManager` es un `ChangeNotifier` separado que nadie
   escuchaba desde la UI) — arreglado con `ListenableBuilder`.
7. **`model_downloader.dart` corregido**: apuntaba a descargar Qwen por
   HTTP (diseño viejo, nunca actualizado tras decidir migrar a Gemma
   embebido en assets). Ahora copia `assets/models/assistant.gguf` al
   storage privado en el primer arranque.
8. **Feature nueva pedida por el usuario**: que el asistente "actúe como
   una IA normal" — el LLM ahora puede responder charla libre
   (`{"chat":"..."}`) además de proponer operaciones
   (`{"tool":...,"args":...}"}`), en un solo prompt.
9. **Bug real reportado y arreglado**: el parser no tenía memoria entre
   turnos — responder "producto" a "¿qué querés hacer?" y luego "crear"
   solo, fallaba porque el segundo mensaje no traía ninguna entidad en su
   propio texto. Se agregó `ConversationContext`, que las pantallas
   pasan entre llamadas a `parse()`.

Total: **111 tests de Dart pasando**, `flutter analyze` sin errores.

## Verificado end-to-end en esta sesión (no solo tests unitarios)

- Pipeline completo del diagramador → export → backend Spring Boot con
  UAP → Docker → respuestas HTTP reales.
- App móvil compilada, instalada y corriendo en un dispositivo Android
  físico real (no emulador).
- Conexión real por USB (`adb reverse`) entre el teléfono y el backend
  generado corriendo en la PC.
- LLM local (Gemma 3 1B) cargando y generando texto en el dispositivo
  real (lento, pero funcional).
- Conversación de varios turnos con contexto (entidad recordada entre
  mensajes) probada en el dispositivo real.

## Problemas pendientes / limitaciones conocidas

- **Rendimiento del LLM en el chip de prueba** (Snapdragon 662, sin GPU):
  funcional pero notablemente lento. Alternativa disponible si hace falta:
  volver a Qwen2.5-1.5B, ya probado en una iteración anterior del proyecto.
- Bug menor: el pluralizador simplista de `uap_generator.py` duplica la
  "s" en nombres que ya terminan en "s" (ej. `"atmtransactionss"`). No
  bloqueante, no arreglado todavía.
- No se probó el ciclo offline-first completo (crear/editar sin conexión,
  sincronizar al volver) en un dispositivo físico real, solo con
  `sqflite_common_ffi` en el test runner de escritorio.
- La UI específica por dominio del backend generado no existe todavía —
  es trabajo planeado para el día del examen, no de esta etapa.
- Problemas heredados de sesiones previas, no revisados en esta etapa:
  falta de autenticación en `POST /diagrams/{id}/export-download`, sin
  endpoint de sign-up activo, sin refresh token, inconsistencia de
  nombres de campo español/inglés entre endpoints del diagramador (ver
  `CONTRATOS_API.md`).

## Reglas que rigieron este trabajo (confirmadas explícitamente por el usuario)

- **No tocar el diagramador FastAPI/React** — está terminado y funcional.
- **El LLM local es una sola instancia fija**, embebida en el APK, no se
  regenera por backend — lo que varía por backend es el contrato UAP
  descubierto en runtime.
- **La UI del backend generado se construye el día del examen**, según el
  diagrama real que se dibuje ahí — no antes, no con datos de prueba.
