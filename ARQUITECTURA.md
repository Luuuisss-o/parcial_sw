# Arquitectura del proyecto

Editor colaborativo de diagramas de clases UML que genera un backend Spring Boot listo para correr a partir del diagrama. Hecho para un examen de Ingeniería de Software.

## Las 4 partes

```
parcial_sw/
├── backend/     FastAPI + PostgreSQL — API del editor, WebSocket colaborativo, IA
├── frontend/    React + Vite — el editor visual de diagramas (navegador)
├── exporters/   Generador Python — diagrama (JSON) → proyecto Spring Boot completo
└── mobile/      Flutter — app para el examen, con asistente de IA 100% offline
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
      ├──▶ Gemini (Google AI) — asistente de edición por texto/voz, lectura de fotos
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

La app **mobile** (Flutter) habla con el **mismo backend FastAPI** que el frontend web — mismos endpoints REST, mismo WebSocket. La diferencia es que el asistente de IA en mobile corre localmente en el teléfono (sin red), mientras que en la web usa Gemini.

## Por qué está separado así

- **`exporters/` vive dentro del repo del backend pero es un módulo aparte**: el router `backend/app/routers/export.py` lo importa como si fuera una librería (`sys.path.append` al `PROJECT_ROOT`). No es un microservicio, es código Python que corre en el mismo proceso del backend cuando alguien pide exportar.
- **El backend Spring Boot generado nunca corre dentro de este proyecto**: se genera, se descarga como ZIP, y el usuario lo levanta en su propia carpeta con su propio Docker Compose. Por eso usa puertos distintos (8090/5434) a los del diagramador (8000/5433) — pueden convivir corriendo al mismo tiempo sin chocar.
- **Mobile no depende de exporters ni de nada Java**: solo consume la misma API REST/WebSocket que ya expone el backend para la web.

## Cómo levantar cada pieza

**Diagramador completo (backend + frontend + su base):**
```bash
docker compose up -d --build
```
Desde la raíz del proyecto. Necesita un `.env` en la raíz con al menos `GEMINI_API_KEY` (ver `docker-compose.yml` para el resto de las variables con sus defaults).

**Backend Spring Boot exportado** (después de descargarlo desde el editor):
```bash
docker compose up -d --build
```
Desde la carpeta donde se descomprimió el ZIP — trae su propio `docker-compose.yml`, generado a medida.

**App móvil:** ver `mobile/README.md` (instalación de Flutter, generación de la carpeta `android/`, pasos para correr en un teléfono físico).

Para el detalle técnico completo (endpoints, tablas, variables de entorno, estado de cada parte), ver `CONTEXTO_PROYECTO.md`.
