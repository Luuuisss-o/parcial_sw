# Cómo empezar una sesión nueva (ahorro de tokens)

> Copia actualizada del `COMO_EMPEZAR_SESION.md` de la raíz. Apunta a los documentos de `docs/contexto/`, que son los que se deben usar de ahora en adelante (más actualizados y granulares que los tres archivos sueltos de la raíz).

Copiá y pegá el mensaje que corresponda al arrancar una sesión nueva de Claude Code en este proyecto. Ajustá el "sobre qué" a la tarea del día.

## Para seguir trabajando en el proyecto (caso más común)

```
Leé docs/contexto/CONTEXTO_PROYECTO.md y docs/contexto/ARQUITECTURA.md antes de arrancar. Hoy quiero trabajar en: [tema concreto, ej. "el endpoint de voz" o "la pantalla de login en mobile"].
```

## Para un bug puntual

```
Leé docs/contexto/CONTEXTO_PROYECTO.md. Tengo un bug: [descripción exacta + captura si hay]. No toques nada más del proyecto, solo esto.
```

## Para revisar algo específico (no todo el proyecto)

```
Leé docs/contexto/CONTEXTO_PROYECTO.md. Revisá [archivo o feature puntual, ej. "docs/contexto/CONTEXTO_BACKEND.md" si es backend], no hace falta que mires el resto del proyecto.
```

## Para retomar la app móvil

```
Leé docs/contexto/CONTEXTO_MOBILE.md (nota: mobile/android/ y pubspec.lock ya existen, no está "sin compilar" como decía la doc vieja). Seguimos con: [ej. "probar flutter run por primera vez"].
```

## Para trabajar en la funcionalidad de voz (web)

```
Leé docs/contexto/CONTEXTO_PROYECTO.md sección 2 y docs/contexto/CONTEXTO_BACKEND.md. La funcionalidad de voz (backend/app/routers/voice.py + services/voice_transcribe.py + frontend/src/api/voice.js + AiAssistantPanel.jsx) está registrada en main.py pero no probada en ejecución. Quiero: [ej. "probarla end-to-end" o "corregir el docstring desactualizado de ai_assistant.py"].
```

## Para generar documentación académica UML (requisitos, casos de uso, diagramas, etc.)

```
Leé docs/contexto/CONTEXTO_DOCUMENTACION.md completo — tiene los casos de uso reales identificados, la matriz de trazabilidad y las advertencias sobre qué NO inventar. Generá: [ej. "el diagrama de casos de uso" o "el documento de requisitos"].
```

## Al cerrar una sesión donde cambiaste algo importante

```
Actualizá docs/contexto/ESTADO_ACTUAL.md con los cambios de hoy antes de terminar. Si el cambio afecta arquitectura o contratos de API, actualizá también el archivo de docs/contexto/ correspondiente.
```

---

## Reglas generales para ahorrar tokens

- **Una sesión = una tarea.** Cuando termine, cerrá y abrí una nueva para lo siguiente.
- **Nunca me cuentes el historial del proyecto de memoria** — decime que lea el archivo de `docs/contexto/` correspondiente, es más preciso y más barato.
- **Sé específico en el pedido.**
- **Las pruebas visuales simples hacelas vos en el navegador.**
- **Si la sesión se pone larga y ya resolviste el tema principal, cerrala.**
- **No confíes ciegamente en `CONTEXTO_PROYECTO.md`/`ARQUITECTURA.md`/`COMO_EMPEZAR_SESION.md` de la raíz** — son la versión histórica. Los de `docs/contexto/` son los actualizados; si hay una contradicción entre ambos, la de `docs/contexto/` refleja una verificación más reciente contra el código real (ver `CONTEXTO_MOBILE.md` para un ejemplo concreto de contradicción ya detectada).
