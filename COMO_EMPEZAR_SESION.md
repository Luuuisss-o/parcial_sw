# Cómo empezar una sesión nueva (ahorro de tokens)

Copiá y pegá el mensaje que corresponda al arrancar una sesión nueva de Claude Code en este proyecto. Ajustá el "sobre qué" a la tarea del día.

## Para seguir trabajando en el proyecto (caso más común)

```
Leé CONTEXTO_PROYECTO.md y ARQUITECTURA.md antes de arrancar. Hoy quiero trabajar en: [tema concreto, ej. "el endpoint de exportar XMI" o "la pantalla de login en mobile"].
```

## Para un bug puntual

```
Leé CONTEXTO_PROYECTO.md. Tengo un bug: [descripción exacta + captura si hay]. No toques nada más del proyecto, solo esto.
```

## Para revisar algo específico (no todo el proyecto)

```
Leé CONTEXTO_PROYECTO.md. Revisá [archivo o feature puntual], no hace falta que mires el resto del proyecto.
```

## Para retomar la app móvil

```
Leé CONTEXTO_PROYECTO.md, sección 7 (Mobile) y 16 (Próximos pasos). Seguimos con: [ej. "generar android/ y compilar por primera vez"].
```

## Al cerrar una sesión donde cambiaste algo importante

```
Actualizá CONTEXTO_PROYECTO.md con los cambios de hoy antes de terminar.
```

---

## Reglas generales para ahorrar tokens

- **Una sesión = una tarea.** Cuando termine, cerrá y abrí una nueva para lo siguiente. No sigas acumulando temas distintos en la misma sesión larga.
- **Nunca me cuentes el historial del proyecto de memoria** — decime que lea `CONTEXTO_PROYECTO.md`, es más preciso y más barato que vos escribiendo un resumen largo.
- **Sé específico en el pedido.** "Revisá el login" es más barato que "revisá que todo funcione bien". Cuanto más acotado el pedido, menos archivos tengo que leer para responder.
- **Las pruebas visuales simples (¿se ve bien el botón?, ¿cargó la página?) hacelas vos en el navegador.** Pedime a mí el navegador solo para bugs que vos no puedas reproducir o diagnosticar fácil.
- **Si la sesión se pone larga y ya resolviste el tema principal, cerrala.** No seas conservador dejándola abierta "por las dudas" — abrir una nueva y decirle que lea el contexto es barato.
