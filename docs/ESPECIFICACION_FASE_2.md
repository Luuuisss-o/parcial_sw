# Especificación de Requerimientos - Fase 2 (revisada)

> Versión revisada de la especificación original, contrastada con la explicación
> oral del docente (audio de la clase, transcripto el 08/11/2026). Las
> diferencias respecto de la versión original están marcadas con **[Corrección]**
> o **[Nuevo]**, con la cita textual del docente que las justifica.

## Visión general (según el docente)

> "Lo que vamos a hacer es que la IA va a actuar como un desarrollador más. Va a
> ser una especie de moderador, una especie de diseñador o un desarrollador
> senior. [...] Cada uno está en distintos lugares, cada uno tiene su propia
> sesión, pero todos están viendo el mismo tablero [...] La novedad aquí va a
> ser la aparición de la IA."

La IA no es un asistente privado de cada usuario: es **un integrante más del
equipo** dentro del tablero compartido, que conversa con todos en un chat de
grupo.

## Requerimientos categorizados por prioridad

**Prioridad Alta (críticos para la aprobación del flujo principal)**
*   **Chat Grupal Sincronizado:** panel de chat donde todos los colaboradores conectados al diagrama envían y leen mensajes en tiempo real.
*   **IA Orientada al Contexto de Usuario:** la IA identifica qué colaborador le pregunta y dirige su respuesta a esa persona por su nombre. *"No puede responder de manera genérica, siempre tiene que hacer alusión a quién está respondiendo."*
*   **Visibilidad Pública de Consultas:** la pregunta a la IA y su respuesta son visibles para todos los colaboradores. *"Todos, absolutamente todos los que están conectados están mirando la pregunta que hace uno y lo que está respondiendo la IA."*

**Prioridad Media (reglas de negocio y experiencia)**
*   **Rol de Mentoría:** la IA actúa como mentora de diseño de software y responde dudas teóricas (ej. del docente: *"no me acuerdo qué es un atributo derivado"*), no se limita a dibujar el diagrama.
*   **Memoria de Contexto Híbrida:** *"La IA mantiene el contexto en general, pero también es capaz de distinguir consultas individuales de cada uno."*
*   **[Nuevo] Rol de desarrollador senior / moderador:** la IA participa como un integrante más del equipo, no como una herramienta aislada.
*   **[Nuevo] Entrega de soluciones configurable:** *"La IA va a tener la capacidad también de entregar soluciones cuando así se lo requieran. Eso va a ser configurable."* Cualquier desarrollador puede pedirle a la IA que haga algo; si se le pide una solución de diseño (ej. "armame el diagrama de una veterinaria") la IA puede entregarla y construirla, siempre que esté habilitado en la configuración del diagrama. Deshabilitado, rige la regla de la Fase 1 (solo ediciones puntuales).
    *   *La especificación original omitía este requerimiento, y la implementación de la Fase 1 lo prohibía explícitamente.*

**Prioridad Baja (opcional / puntos extra)**
*   **[Corrección] Modelo LLM local — "valorable", no obligatorio:** *"Debe ser un modelo local. Sin embargo, esto lo vamos a dejar como valorable. Es decir, no es obligatorio."* El docente advierte que *"el modelo tiene que ser un modelo poderoso. Un modelo simple no se va a poder"*, que un modelo mediano necesita hardware, y propone como alternativas *"algo similar a Google Colab para arriba"* o, si no es posible, *"cualquier otro modelo"* (cuenta universitaria de Google AI Studio).
    *   *El audio no menciona que el modelo deba correr en el celular ni que deba estar entrenado/personalizado (fine-tuning). Pendiente de confirmar con el docente antes de implementarlo de esa forma.*

---

## Casos de Uso (Fase 2)

*Nota: la documentación de la Fase 1 finaliza en el CU-13; los nuevos casos de uso se numeran desde el CU-14.*

**CU-14. Interactuar en el chat grupal del diagrama**
*   **Actores:** Dueño, Colaborador.
*   **Propósito:** comunicación escrita en tiempo real entre los miembros del equipo dentro del lienzo del diagrama.
*   **Resumen:** el usuario escribe en el panel de chat. El sistema transmite el mensaje vía WebSocket a todos los usuarios conectados al mismo diagrama, mostrando autor y marca de tiempo. El historial se conserva para quien se conecta más tarde, y el panel muestra quiénes están conectados.
*   **Implementación:** `POST/GET /diagrams/{id}/chat`, evento `chat.message`, evento `presence`; `ChatPanel.jsx`.

**CU-15. Solicitar mentoría teórica o de diseño a la IA**
*   **Actores:** Dueño, Colaborador.
*   **Propósito:** asistencia conceptual sobre ingeniería de software sin salir del entorno de trabajo.
*   **Resumen:** el usuario dirige una pregunta conceptual a la IA en el chat grupal ("@IA ..."). La IA la responde sin modificar el diagrama y con una explicación pedagógica visible para todo el equipo, marcada como "Mentoría".
*   **Implementación:** `classify_intent()` detecta las consultas teóricas y las responde sin herramientas (la IA no puede editar el diagrama en ese modo); `chat_message.ai_mode = "MENTOR"`.

**CU-16. Recibir asistencia de IA contextualizada por usuario**
*   **Actores:** Dueño, Colaborador.
*   **Propósito:** que la IA distinga las consultas concurrentes de varios usuarios y responda de forma personalizada.
*   **Resumen:** al enviar un prompt, el sistema adjunta los metadatos de la sesión (ID / nombre / email). La IA responde aludiendo directamente a quien preguntó, manteniendo coherencia con las consultas previas de ese usuario (hilo individual), con la conversación reciente del equipo y con el estado global del diagrama (contexto global).
*   **Implementación:** `Requester`, `user_ai_history()`, `team_context()`, `address_reply()`; eventos `ai.*` con `request_id` y `requested_by`.

**CU-17. Configurar proveedor de Inteligencia Artificial (Local/Nube)** — *opcional ("valorable")*
*   **Actores:** Dueño (o administrador del sistema).
*   **Propósito:** conmutar entre un servicio de IA basado en API (Gemini / Google AI Studio) y un modelo LLM local o desplegado en un entorno como Google Colab.
*   **Resumen:** se define el *endpoint* y el token de la IA; el sistema enruta las peticiones del asistente (CU-08, CU-15, CU-16) al proveedor elegido sin romper la interfaz de comunicación del backend.
*   **Estado:** pendiente; ver la nota de la Prioridad Baja.

**CU-18. [Nuevo] Configurar la entrega de soluciones de la IA**
*   **Actores:** Dueño (configura), Colaborador (consulta el estado).
*   **Propósito:** decidir si la IA puede entregar soluciones de diseño completas cuando un integrante se las pide.
*   **Resumen:** el dueño del diagrama activa o desactiva la opción desde el panel de chat. Todos los conectados ven el estado actual y quién lo cambió. Activada, la IA diseña y construye la solución pedida (clases, atributos y relaciones), integrándola con lo existente y resumiendo sus decisiones. Desactivada, orienta como mentora y pide que le indiquen qué clases crear.
*   **Implementación:** `diagram.ai_solutions_enabled`, `GET/PATCH /diagrams/{id}/ai/settings` (PATCH solo para el dueño), evento `ai.settings`; `AiSettingsBar.jsx`.
