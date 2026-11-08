# Arquitectura del proyecto

Editor colaborativo de diagramas de clases UML que genera un backend Spring Boot listo para correr a partir del diagrama. Hecho para un examen de Ingeniería de Software.

> Copia actualizada del `ARQUITECTURA.md` de la raíz, con la incorporación del asistente de voz web (Gemini) verificado en esta sesión. El archivo original de la raíz se deja intacto.

## Las 4 partes

```
parcial_sw/
├── backend/     FastAPI + PostgreSQL — API del editor, WebSocket colaborativo, IA (texto + voz)
├── frontend/    React + Vite — el editor visual de diagramas (navegador)
├── exporters/   Generador Python — diagrama (JSON) → proyecto Spring Boot completo
└── mobile/      Flutter — app para el examen, con asistente de IA 100% offline (voz vía Vosk, LLM local)
```

## Cómo se conectan

```
Usuario (navegador)
      │
      ▼
frontend (React, puerto 5173)
      │  REST + WebSocket, vía proxy nginx en /api/
      ▼
backend (FastAPI, puerto 8000)
      │
      ├──▶ PostgreSQL (puerto 5433) — diagramas, clases, atributos, relaciones
      ├──▶ Gemini (Google AI) — asistente de edición por texto, TRANSCRIPCIÓN DE VOZ (nuevo,
      │        POST /voice/transcribe), lectura de fotos
      └──▶ exporters/ (Python, corre dentro del propio backend)
              │
              ▼
      genera un ZIP: proyecto Spring Boot + Dockerfile + docker-compose.yml
      + colección Postman + README
              │
              ▼
      usuario descomprime y levanta ese proyecto aparte
      (Spring Boot puerto 8090, su propio Postgres puerto 5434)
```

La app **mobile** (Flutter) habla con el **mismo backend FastAPI** que el frontend web — mismos endpoints REST, mismo WebSocket. La diferencia es que el asistente de IA en mobile corre localmente en el teléfono (LLM local + reconocimiento de voz Vosk, ambos offline, sin red), mientras que en la web usa Gemini para todo (texto, voz nueva, y fotos). **Son dos implementaciones de voz completamente independientes** — no comparten código ni endpoint.

## Por qué está separado así

- **`exporters/` vive dentro del repo del backend pero es un módulo aparte**: el router `backend/app/routers/export.py` lo importa como si fuera una librería (`sys.path.append` al `PROJECT_ROOT`). No es un microservicio, es código Python que corre en el mismo proceso del backend cuando alguien pide exportar.
- **El backend Spring Boot generado nunca corre dentro de este proyecto**: se genera, se descarga como ZIP, y el usuario lo levanta en su propia carpeta con su propio Docker Compose. Por eso usa puertos distintos (8090/5434) a los del diagramador (8000/5433) — pueden convivir corriendo al mismo tiempo sin chocar.
- **Mobile no depende de exporters ni de nada Java**: solo consume la misma API REST/WebSocket que ya expone el backend para la web.
- **La voz web pasa por el backend, no solo por el navegador**: a diferencia del enfoque anterior (Web Speech API 100% en el cliente), ahora el audio se sube como archivo a `POST /voice/transcribe` y Gemini lo transcribe del lado del servidor. Motivo (según comentarios en el código): la Web Speech API depende de Chrome/Edge y de conexión directa del navegador a servidores de Google, y fallaba seguido sin aviso claro.

## Cómo levantar cada pieza

**Diagramador completo (backend + frontend + su base):**
```bash
docker compose up -d --build
```
Desde la raíz del proyecto. Necesita un `.env` en la raíz con al menos `GEMINI_API_KEY` (usada ahora también por el endpoint de voz, no solo por el asistente de texto y la lectura de fotos).

**Backend Spring Boot exportado** (después de descargarlo desde el editor):
```bash
docker compose up -d --build
```
Desde la carpeta donde se descomprimió el ZIP.

**App móvil:** ver `mobile/README.md`. **Nota (verificado en esta sesión)**: `mobile/android/` y `mobile/pubspec.lock` ya existen en el repo — los pasos de generación inicial descriptos en ese README ya se ejecutaron, aunque el README no fue actualizado para reflejarlo.

Para el detalle técnico completo (endpoints, tablas, variables de entorno, estado de cada parte), ver los archivos de `docs/contexto/` (`CONTEXTO_BACKEND.md`, `CONTEXTO_FRONTEND.md`, `CONTEXTO_MOBILE.md`, `CONTEXTO_BASE_DATOS.md`, `CONTRATOS_API.md`, `ESTADO_ACTUAL.md`).
