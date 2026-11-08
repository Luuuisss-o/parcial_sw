# Contexto del proyecto — parcial_sw

> Documento standalone para que una sesión nueva entienda el proyecto sin depender de conversaciones previas. Actualizado a partir de una revisión completa del código real (backend, frontend, mobile) al 2026-09-20, incluyendo cambios sin commitear (funcionalidad de voz por Gemini). Reemplaza como referencia principal al `CONTEXTO_PROYECTO.md` de la raíz (que se deja intacto como fuente histórica).

## 1. Objetivo del proyecto

Editor colaborativo de diagramas de clases UML, para un examen de Ingeniería de Software. Permite:

- Crear y editar diagramas de clases en tiempo real, con varios usuarios trabajando sobre el mismo diagrama (colaboración vía WebSocket).
- Importar un diagrama dibujado a mano desde una foto (Gemini Vision), con vista previa editable antes de confirmar.
- Editar el diagrama con un asistente de IA por **texto o por voz** (Gemini), con un contrato fijo de "tools" — nunca genera un diseño completo desde una descripción de negocio, solo ejecuta ediciones puntuales.
- Importar y exportar el diagrama en formato XMI 2.1 (compatible con Enterprise Architect).
- Generar un backend Spring Boot completo a partir del diagrama (modelos JPA, repositorios, servicios, controladores REST, DTOs, colección Postman, Dockerfile).
- Una app móvil (Flutter), con asistente de IA por voz/texto 100% offline (LLM local + Vosk), pensada para el día del examen sin depender de internet.

Fuera de alcance: registro de usuarios desde la UI (no hay endpoint de sign-up activo), refresh tokens (no implementado pese a existir la configuración), ejecución del backend Spring Boot generado dentro de este mismo proyecto (se descarga y se levanta aparte).

## 2. Novedad relevante no documentada previamente: asistente por voz (web)

Hay cambios reales sin commitear en el repo (`git status`) que agregan dictado por voz al asistente de IA del editor web, con arquitectura **backend-side** (no la Web Speech API del navegador que existía antes):

- `backend/app/routers/voice.py`: nuevo endpoint `POST /voice/transcribe`, recibe un `UploadFile` de audio (mimetypes permitidos: `audio/webm`, `audio/ogg`, `audio/wav`, `audio/mp4`, `audio/mpeg`; máx 10 MB), requiere JWT (`get_current_user`), y devuelve `{"text": "..."}`.
- `backend/app/schemas/voice.py`: `VoiceTranscribeResult { text: str }`.
- `backend/app/services/voice_transcribe.py`: llama a Gemini (`gemini-3.5-flash`, con fallback a `gemini-3.5-flash-lite` y reintentos ante 503) para transcribir el audio a texto plano en español. Solo transcribe — no interpreta comandos ni toca el diagrama.
- `frontend/src/api/voice.js`: `transcribeAudio(blob)` sube el audio a `/voice/transcribe` (timeout propio de 45s) y devuelve el texto.
- `frontend/src/components/panels/AiAssistantPanel.jsx`: se reemplazó el uso de la Web Speech API del navegador (`window.SpeechRecognition`) por grabación con `MediaRecorder` + subida del blob al backend. El texto transcripto entra al mismo flujo que un comando escrito a mano (`sendAiCommand`).
- **Confirmado registrado en `main.py`**: `app.include_router(voice.router)` está presente (línea 56 del diff), la funcionalidad está conectada de punta a punta a nivel de código.

Motivo del cambio (según comentarios en el propio código): la Web Speech API depende de que el navegador sea Chrome/Edge y de que tenga conexión directa a los servidores de reconocimiento de Google, lo cual "en la práctica falla seguido y sin un motivo claro para el usuario".

**No confirmado**: no se pudo verificar en ejecución (no se corrió Docker/backend en esta sesión) que el endpoint funcione end-to-end; es una revisión de código, no una prueba funcional. Tampoco se confirmó que `GEMINI_API_KEY` esté seteada en el `.env` real (el archivo existe pero no se leyó su contenido).

**Contradicción con documentación previa**: el docstring de `backend/app/services/ai_assistant.py` (archivo no tocado en este cambio) todavía dice "la voz se transcribe en el cliente (Web Speech API)" — quedó desactualizado por este cambio y debería corregirse en el propio código (no se modifica en esta tarea, solo se señala).

**Importante — mobile no tiene relación con este cambio**: la app Flutter ya tenía su propio mecanismo de voz, completamente distinto: reconocimiento offline con Vosk (`speech_service.dart`) + LLM local (`local_llm_service.dart`), sin backend ni Gemini de por medio. Son dos implementaciones de voz independientes para dos plataformas distintas.

## 3. Arquitectura

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
puerto 5433     asistente de texto/voz,     interno, corre en el mismo
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

El frontend en producción (Docker) sirve estáticos con nginx, que hace proxy de `/api/` hacia el backend (confirmado: existe `frontend/nginx.conf`). En desarrollo local (`npm run dev`) el navegador habla directo al backend en 8000.

No hay otros servicios externos además de Gemini (Google AI), usado para: asistente de texto, transcripción de voz (nuevo), y lectura de fotos.

## 4. Tecnologías

**Backend**: Python, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 (`pydantic-settings`), `python-jose` (JWT), `passlib`+bcrypt, `google-genai`. PostgreSQL 16.

**Frontend**: React 19, Vite, `react-router-dom`, `axios`, `zustand`. Servido en producción con nginx.

**Exporters**: Python + Jinja2. Genera Java 17 + Spring Boot 3.2.4 (Maven).

**Mobile**: Flutter/Dart. `http`, `web_socket_channel`, `provider`, `shared_preferences`, `llamadart` (LLM local vía llama.cpp), `vosk_flutter_2` (voz offline).

**Infraestructura**: Docker + Docker Compose.

## 5. Estructura del repo

```
parcial_sw/
├── backend/app/
│   ├── routers/     endpoints REST y WebSocket (incluye voice.py, nuevo)
│   ├── models/       user.py, uml.py
│   ├── schemas/       uno por recurso (incluye voice.py, nuevo)
│   ├── services/      ai_assistant.py, ai_tools.py, xmi.py, locks.py, diagram_vision.py, voice_transcribe.py (nuevo)
│   ├── core/          config.py, security.py
│   └── main.py        arma la app y registra routers (incluye voice.router)
├── backend/alembic/versions/   3 migraciones
├── frontend/src/
│   ├── pages/         Login, Home, Diagram
│   ├── components/    canvas/, panels/ (incluye AiAssistantPanel.jsx modificado)
│   ├── hooks/
│   ├── api/            un archivo por recurso (incluye voice.js, nuevo)
│   └── store/          auth.js, locks.js, undo.js
├── exporters/          generador Spring Boot
├── mobile/lib/         screens/, services/, models/ — TIENE android/ y pubspec.lock (ver sección Mobile)
├── docs/contexto/      ESTA carpeta, nueva
└── docker-compose.yml
```

## 6. Backend — resumen (detalle en CONTEXTO_BACKEND.md)

FastAPI con capas: `routers/` → `services/`/lógica inline → `models/` (SQLAlchemy) → PostgreSQL. `_helpers.py` centraliza `_accessible_diagram_filter(me)`.

Routers activos (confirmado en `main.py`): `auth`, `diagramas`, `classes`, `atributos`, `metodo`, `relacion`, `export`, `ai`, `xmi`, `vision`, `voice` (nuevo), `realtime` (WebSocket).

## 7. Frontend — resumen (detalle en CONTEXTO_FRONTEND.md)

React + Vite, hooks custom por feature, `zustand` para sesión. `AiAssistantPanel.jsx` ahora graba audio con `MediaRecorder` en vez de usar la Web Speech API nativa.

## 8. Mobile — estado real (IMPORTANTE, contradice el CONTEXTO_PROYECTO.md original)

El documento original de la raíz afirma: *"Nunca se compiló. No existe mobile/android/, no existe mobile/ios/, no hay pubspec.lock"* y que *"Todo mobile/ está sin trackear en git"*.

**Esto ya no es así.** Verificado en esta sesión:
- `mobile/android/` **SÍ existe**, con proyecto Gradle completo (`build.gradle.kts`, `AndroidManifest.xml`, `MainActivity.kt`, `gradlew`, recursos `mipmap-*`, etc.).
- `mobile/pubspec.lock` **SÍ existe**.
- `mobile/ios/` sigue sin existir (no confirmado que se haya intentado).
- Existen artefactos de `flutter pub get` (`.dart_tool/package_config.json`, `.flutter-plugins-dependencies`).

**No confirmado**: si el proyecto compila y corre de punta a punta (no se ejecutó `flutter run` ni `flutter build` en esta sesión — es revisión de código y de archivos en disco, no una prueba de build). Tampoco se confirmó si `mobile/` ya está agregado a git o sigue untracked (el `git status` del inicio de esta sesión no lista archivos de `mobile/`, lo cual podría significar que ya está trackeado y sin cambios pendientes, o que sigue en `.gitignore`; no se verificó cuál de las dos).

Esta es una contradicción real y significativa entre la documentación previa y el estado actual del código — ver también `ESTADO_ACTUAL.md`.

## 9. Base de datos — resumen (detalle en CONTEXTO_BASE_DATOS.md)

PostgreSQL 16. Tablas: `user`, `diagram`, `diagram_collaborator`, `clase`, `relacion`, `atributo`, `metodo`. 3 migraciones Alembic, ninguna relacionada con voz (el endpoint de voz no persiste nada en base de datos).

## 10. Autenticación y autorización

JWT (`python-jose`), claims `sub` (email), `kind="access"`, `iat`, `exp`. `get_current_user` exige `Authorization: Bearer`. El nuevo endpoint `/voice/transcribe` también exige `get_current_user` (confirmado en el código), igual que `/vision/detect`. No hay refresh token implementado. No hay endpoint de sign-up activo.

## 11. Servicios externos

Únicamente Gemini (Google AI), usado en tres puntos del backend: `ai_assistant.py` (comandos de texto, modelo `gemini-3.5-flash-lite`, vía `client.interactions.create`), `diagram_vision.py` (lectura de fotos), y `voice_transcribe.py` (nuevo, transcripción de audio, modelo `gemini-3.5-flash` con fallback `gemini-3.5-flash-lite`, vía `client.models.generate_content`). Nótese que `ai_assistant.py` usa una API distinta del SDK (`interactions.create`) que `voice_transcribe.py`/`diagram_vision.py` (`generate_content`) — ambas conviven en el mismo backend, no es un error, son dos capas de la misma librería `google-genai`.

## 12. Estado actual

Ver `ESTADO_ACTUAL.md` para el detalle día a día. Resumen: el diagramador (backend+frontend+Postgres) fue verificado funcionando en sesiones previas (según el CONTEXTO_PROYECTO.md original, no re-verificado en esta sesión). La funcionalidad de voz vía Gemini es código nuevo sin commitear, registrado en `main.py`, no probado en ejecución en esta sesión.

## 13. Decisiones técnicas importantes

- El asistente de IA (texto y ahora voz) nunca genera un diagrama completo desde una descripción de negocio — restricción explícita de la cátedra, reforzada en el `SYSTEM_PROMPT` de `ai_assistant.py`.
- La detección desde foto y ahora también la transcripción de voz nunca aplican cambios directo: la foto siempre pasa por una vista previa editable (`/vision/detect` → revisión → `/vision/apply`); la voz se transcribe a texto y ese texto se manda como si el usuario lo hubiera tipeado, pasando por el mismo flujo asíncrono de `/diagrams/{id}/ai/command`.
- Los nombres de clase/atributo se normalizan a identificadores Java válidos únicamente en el pipeline de exportación, nunca en la base de datos.
- Puertos fijos y separados entre el diagramador (8000/5433/5173) y cualquier backend Spring Boot exportado (8090/5434).
- Nombres de campo inconsistentes entre endpoints (español/inglés) a propósito, ver `CONTEXTO_BACKEND.md`.

## 14. Funcionalidades terminadas (según código, confirmado por lectura)

- CRUD de diagramas, clases, atributos, métodos, relaciones.
- Colaboración en tiempo real (WebSocket): locks por clase, cursores en vivo.
- Login con JWT.
- Asistente de IA por texto.
- **Asistente de IA por voz (web, nuevo)**: grabación de audio en el navegador → transcripción por Gemini en el backend → mismo flujo que un comando de texto. Registrado en `main.py`, no probado en ejecución.
- Importar diagrama desde foto (Gemini Vision) con vista previa editable.
- Exportar/importar XMI 2.1.
- Generación de backend Spring Boot.
- Conversión a "clase de asociación" (UML 2.5).
- Mobile: código Dart completo, incluyendo asistente de voz/texto offline (Vosk + LLM local), y ahora con `android/` generado y `pubspec.lock` presente (no confirmado que compile).

## 15. Funcionalidades pendientes / no confirmadas

- Confirmar en ejecución que `/voice/transcribe` funciona (requiere `GEMINI_API_KEY` válida en `backend/.env`, no verificado su contenido).
- Confirmar si mobile compila realmente (`flutter run`/`flutter build` no ejecutado en esta sesión pese a que `android/` y `pubspec.lock` ya existen).
- Confirmar si `mobile/` está trackeado en git actualmente (el git status inicial no lo menciona, lo cual es ambiguo).
- Endpoint de sign-up (no existe, pese al schema `SignUpIn`).
- Refresh token (no implementado).
- `frontend/README.md` sigue siendo el boilerplate default de Vite, sin documentar el proyecto real.

## 16. Problemas conocidos

- Inconsistencia de nombres de campo español/inglés entre endpoints (ver `CONTEXTO_BACKEND.md` y `CONTRATOS_API.md`).
- Docstring desactualizado en `ai_assistant.py` (dice que la voz se transcribe en el cliente, ya no es así).
- Documentación previa (`CONTEXTO_PROYECTO.md` de la raíz) desactualizada respecto al estado real de `mobile/` (ver sección 8).
- `export.py` (`POST /diagrams/{id}/export-download`) no valida que el diagrama sea accesible para el usuario autenticado — de hecho ni siquiera exige autenticación (no usa `get_current_user`, a diferencia de todos los demás routers). No confirmado si esto es intencional o un descuido; es una observación de este audit, no un hecho documentado previamente.
