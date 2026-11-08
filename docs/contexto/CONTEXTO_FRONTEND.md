# Contexto frontend — parcial_sw

## Arquitectura

React 19 + Vite. Estado por feature vía hooks custom (`useClassesAndDetails`, `useRelations`, `useLocks`, `useLiveCursors`, `useAutoSave`, `useExport`, `useDiagram`, `useDebouncedCallback`, `useTheme`). Estado de sesión global con `zustand` (`store/auth.js`, más `store/locks.js` y `store/undo.js`).

## Rutas (`src/App.jsx`)

- `/login` → `pages/Login.jsx` (pública).
- `/` → `pages/Home.jsx`, protegida por `Protected` (lee `useAuth(s => s.token)`, redirige a `/login` si no hay token).
- `/diagram/:id` → `pages/Diagram.jsx`, protegida.
- `*` → redirect a `/`.

## Páginas (`src/pages/`)

- `Login.jsx`, `Home.jsx` (lista de diagramas), `Diagram.jsx` (el editor).

## Componentes (`src/components/`)

- `canvas/`: `Sheet.jsx` (contenedor del lienzo), `ClassCard/` (`ClassCard.jsx`, `Header.jsx`, `Body.jsx`, `Ports.jsx`), `ConnectionLayer.jsx` (relaciones en SVG).
- `panels/`: `Inspector.jsx`, `RelationInspector.jsx`, `AiAssistantPanel.jsx` (modificado — ver abajo), `ImportFromPhotoModal.jsx`, `CollaboratorsModal.jsx`, `AssociationClassModal.jsx`.
- `layout/`: `HeaderBar.jsx`, `LeftPanel.jsx`.
- `common/`: `Icon.jsx`, `ApiStatusBadge.jsx`, `HelpGuide.jsx`.

## Servicios / API (`src/api/`)

Un archivo por recurso, todos consumen `api/client.js`: `classes.js`, `relations.js`, `diagrams.js`, `ai.js`, `vision.js`, `xmi.js`, `export.js`, `realtime.js`, **`voice.js` (nuevo)**.

- `api/client.js`: instancia `axios`, `baseURL = API_URL` (de `src/config.js`), `timeout: 10000` global. Interceptor de request agrega `Authorization: Bearer`. Interceptor de response desloguea automáticamente en 401 (`useAuth.getState().logout()` + redirect a `/login`). Loguea cada request/response por `console.log`/`console.error` (código de desarrollo, no confirmado si se desactiva en producción).
- `api/ai.js`: `sendAiCommand(diagramId, text)` — `POST /diagrams/{id}/ai/command`, el resultado real llega por WebSocket (`ai.done`/`ai.error`), no en la respuesta HTTP (202).
- `api/vision.js`: `detectDiagramFromImage(file)` (`POST /vision/detect`, timeout propio 90s), `applyDetectedDiagram({title, classes, relations})` (`POST /vision/apply`).
- `api/voice.js` (nuevo): `transcribeAudio(blob)` — arma un `FormData` con el blob como `audio.webm`, `POST /voice/transcribe`, timeout propio 45s, devuelve `res.data.text`.

## Componente modificado: `AiAssistantPanel.jsx`

Antes: usaba `window.SpeechRecognition`/`window.webkitSpeechRecognition` (Web Speech API nativa del navegador) para dictado, con reconocimiento y transcripción hechos enteramente en el cliente.

Ahora: graba audio con `MediaRecorder` (`navigator.mediaDevices.getUserMedia({audio: true})`), junta los chunks en un `Blob`, y al soltar el botón de grabar llama a `transcribeAudio(blob)` (de `api/voice.js`). El texto que vuelve se pasa a la misma función `send()` que ya usaba el input de texto, que a su vez llama a `sendAiCommand`.

Estados nuevos: `transcribing` (booleano, deshabilita el input y el botón mientras se sube/transcribe el audio), reemplaza al viejo `recognitionRef` por `mediaRecorderRef` + `audioChunksRef`.

Manejo de errores: si `getUserMedia` falla (permiso denegado o navegador sin soporte), o si `transcribeAudio` rechaza (por ejemplo 422 "no se entendió nada", 503 "mucha demanda", 400 mimetype inválido), el mensaje de error (`err.response.data.detail`) se agrega al log de la conversación con `role: "error"`.

No se modificó el flujo de comandos de texto ni el de recepción de resultados por WebSocket (`onEvent("ai.done"/"ai.error")`).

## Autenticación (`store/auth.js`)

Zustand store: `token`, `user` (payload JWT decodificado con `jwt-decode`), `email`. Persiste `token` y `email` en `localStorage` (`uml_access_token`, `uml_email`). Expone helpers fuera de componentes: `getToken()`, `getEmail()`, `isAuthenticated()` — usados por el interceptor de `client.js`.

## Interfaces / modelos

No hay TypeScript. El mapeo backend→frontend se hace con funciones helper por archivo (ej. `mapClass()` en `api/classes.js`, no leído en detalle en este audit) porque el backend devuelve nombres de campo en español o inglés según el endpoint (ver `CONTRATOS_API.md`).

## Funcionalidades implementadas (frontend)

- CRUD visual de clases, atributos, métodos, relaciones (drag & drop en grilla, según `ClassCard`/`Sheet`/`ConnectionLayer` — no se auditó el detalle de interacción).
- Colaboración en tiempo real: locks visuales por clase, cursores en vivo (`useLiveCursors`, `useLocks`).
- Asistente de IA por texto y **ahora por voz** (grabación + transcripción backend).
- Importar diagrama desde foto (`ImportFromPhotoModal.jsx` + `api/vision.js`).
- Exportar/importar XMI, exportar a Spring Boot (`useExport.js` + `api/xmi.js`/`api/export.js`).
- Gestión de colaboradores (`CollaboratorsModal.jsx`).
- Conversión a clase de asociación (`AssociationClassModal.jsx`).

## Archivos importantes

- `frontend/src/api/client.js`, `frontend/src/store/auth.js`, `frontend/src/App.jsx`.
- `frontend/src/components/panels/AiAssistantPanel.jsx` (modificado, ver arriba).
- `frontend/src/api/voice.js` (nuevo).
- `frontend/nginx.conf` (confirmado que existe, contenido no leído en detalle en este audit — documentado como proxy `/api/` según `ARQUITECTURA.md`/`CONTEXTO_PROYECTO.md` previos, no re-verificado línea por línea).

## Estado actual

`frontend/README.md` es el boilerplate default de `create vite` (no documenta el proyecto real — problema de documentación, no de código). El resto del frontend está implementado y coherente con lo que consume del backend, incluida la nueva integración de voz vía `api/voice.js`. No se ejecutó `npm run dev`/build en esta sesión — es revisión de código, no prueba funcional.
