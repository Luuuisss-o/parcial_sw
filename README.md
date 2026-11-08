# UML Collab Tool

Editor colaborativo de diagramas de clases UML con generación de backend Spring Boot,
asistente de IA para edición por voz/texto, interoperabilidad XMI con Enterprise Architect,
y app móvil con IA local offline.

Migrado y reorganizado a partir del prototipo original (`uml-ai-tool`), conservando lo
funcional (backend FastAPI + WebSockets, frontend React del canvas, exportador a Spring Boot)
y reconstruyendo desde cero lo que faltaba: asistente de IA, XMI, mutual exclusion y app móvil.

## Estructura

- `backend/` — FastAPI + SQLAlchemy + PostgreSQL + WebSockets (colaboración en tiempo real).
- `frontend/` — React + Vite, canvas de diagramación (Sheet/ClassCard/ConnectionLayer).
- `exporters/` — Pipeline de generación de código: diagrama → JSON → proyecto Spring Boot.
- `mobile/` — (pendiente) App Flutter/React Native con asistente de voz offline.

## Setup rápido

```bash
cd backend
copy .env.example .env
# editar .env con credenciales locales
```

Ver detalles de cada subsistema en su propio README.

## Despliegue en producción

Un solo comando en un servidor Ubuntu (AWS EC2) con dominio DuckDNS y HTTPS:
ver [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) y `deploy/setup_ec2.sh`.
