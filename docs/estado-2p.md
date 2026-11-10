# Estado del segundo parcial (CU-01 … CU-09)

Auditoría e implementación según `PLAN_DESARROLLO_2P.md`, 10/11/2026, rama
`claude/exciting-tesla-sscl8u`. Se extendió el producto del primer parcial: no hay una app
paralela. Cada estado se respalda con una prueba **ejecutada**.

## Resumen

| ID | Caso de uso | Estado | Evidencia |
|---|---|---|---|
| CU-01 | IA dentro de la sesión colaborativa | **COMPLETA** | El asesor vive en el chat del equipo del editor; probado con 3 sesiones en Chrome |
| CU-02 | Chat compartido en tiempo real | **COMPLETA** | 3 sesiones ven pregunta y respuesta sin recargar; historial persistido y recuperado al reingresar |
| CU-03 | Respuesta individual, visible para todos | **COMPLETA** | La respuesta nombra y se dirige a quien preguntó (`addressed_to`, `reply_to`); todos la leen |
| CU-04 | Contexto del diagrama y la conversación | **COMPLETA** | Clases, atributos, relaciones **con multiplicidades**; hilo propio + conversación del equipo; aislamiento entre diagramas probado |
| CU-05 | Asesor sénior de diseño | **COMPLETA** | Con Gemini real detecta cardinalidades incorrectas y explica la solución sobre las clases reales |
| CU-06 | Propuestas de cambios estructuradas | **COMPLETA** | Operaciones validadas contra el diagrama vigente, mostradas con su impacto, **sin modificar nada** |
| CU-07 | Aplicar propuestas con autorización | **COMPLETA** | Acepta quien preguntó o el dueño; se aplica una sola vez por el servicio de operaciones; “desactualizada” si cambiaron las clases involucradas |
| CU-08 | Configurar la participación del asesor | **COMPLETA** | Asesor activo/inactivo, propuestas sí/no, entrega de soluciones, proveedor; modo **a demanda**; persistido y visible para todos |
| CU-09 | El primer parcial sigue funcionando | **COMPLETA** | 192 pruebas del primer parcial siguen en verde; integración del móvil 3/3 |

Pruebas al cerrar: backend + generador **209/209** (incluidas las que llaman a Gemini real),
móvil **133/133**, E2E en navegador con 3 sesiones y Gemini real **25/25**.

Re-verificación del 10/11/2026 (con el modelo propio, HTTPS y la app nueva): backend + generador
**220/220** dos veces seguidas, con Gemini real y una base nueva aislada; móvil **130/130**
(3 omitidas); la web compila. En producción: migración en `head`, modelo v2 respondiendo por
HTTPS desde el backend (revisión con propuesta, mentoría sin acciones y edición correctas).

## Qué existía y qué se agregó

Ya existía (Fase 2, `docs/ESPECIFICACION_FASE_2.md`): chat grupal persistido por diagrama,
consultas `@IA` públicas dirigidas a quien pregunta, mentoría, memoria híbrida (hilo propio +
equipo), entrega de soluciones configurable y proveedor de IA configurable (Gemini o un modelo
propio compatible con OpenAI, incluido uno servido desde Colab).

Se agregó en este parcial:

| Pieza | Dónde |
|---|---|
| Propuestas del asesor (tabla `ai_proposal`, validación, huella, aplicar/rechazar) | `backend/app/services/ai_proposals.py`, `routers/ai.py` (`/ai/proposals`) |
| Asesor separado del editor: en modo asesor solo recibe la herramienta `propose_changes` | `services/ai_assistant.py` (`_advisor_reply`) |
| Los proveedores usan exactamente las herramientas recibidas (antes siempre el juego completo de edición) | `services/llm_providers.py` |
| Estado persistido de cada consulta (`pending/running/device/completed/failed`) | `chat_message.ai_status`, `services/chat_service.py` |
| Recuperación de consultas cortadas por un reinicio del servidor | `chat_service.recover_interrupted_questions()` (al arrancar) |
| Límite de uso: una consulta en curso por persona y diagrama (429) | `routers/chat.py`, `routers/ai.py` |
| Asesor activable y propuestas activables (`ai_enabled`, `ai_proposals_enabled`) | migración `f7b2c9d4e1a6`, `AiSettingsBar.jsx` |
| Multiplicidades en el contexto del modelo; contexto compacto para diagramas grandes | `ai_tools.snapshot()`, `ai_assistant.compact_state()` |
| Aviso si el diagrama cambió mientras el asesor respondía | `chat_service.run_ai_question_background` |
| Tarjeta de propuesta en el chat (estado, cambios, Aplicar/Rechazar) | `frontend/src/components/panels/ProposalCard.jsx` |

## Garantías del asesor (probadas)

- **No edita por su cuenta:** en modo asesor el modelo no tiene herramientas de edición; si
  intenta usar una, se rechaza (`test_herramientas_de_edicion_no_se_aceptan_en_modo_asesor`).
- **No inventa:** si dice que dejó una propuesta sin haberla registrado, se le insiste una vez y,
  si no la registra, la respuesta lo aclara. Si la propuesta es inválida (clase inexistente,
  relación duplicada…), se le devuelve el error para que la corrija.
- **Se ancla al modelo real:** si el texto no nombra ninguna clase de la propuesta, se agrega el
  detalle de los cambios.
- **Concurrencia:** aceptar es una transición atómica (`proposed → applying`): dos personas que
  aceptan a la vez no la aplican dos veces (la segunda recibe 409).
- **Sin aplicar a ciegas:** la propuesta guarda una huella de las clases y relaciones que toca; si
  cambiaron al aceptarla, queda **desactualizada**. Los cambios en otras clases no la invalidan.
- **Resiliencia:** si el proveedor de IA no responde, la consulta queda “fallida” con un mensaje
  dirigido al autor; el chat y el diagrama siguen funcionando.

## Decisiones donde el audio era ambiguo

| Tema | Decisión |
|---|---|
| “IA configurable” | Modo **a demanda** (responde cuando se la consulta), activable por el dueño, con propuestas activables. **No** se implementaron sugerencias espontáneas: el plan las marca como opcionales y, si se agregan, deben ser opt-in y sin edición automática. |
| “Dar soluciones” | Dos caminos separados: la IA de edición ejecuta órdenes explícitas (“creá la clase X”, primer parcial); el asesor **propone** y un humano aplica. La entrega de soluciones completas sigue siendo configurable (Fase 2). |
| Quién aplica una propuesta | Quien hizo la consulta o el dueño del diagrama. El resto la ve, pero no la decide. |
| Modelo local para el editor | No obligatorio, pero **implementado**: el dueño elige *Modelo propio del equipo* (Gemma 3 1B entrenado, servido con llama.cpp en un servidor propio) o cualquier servidor compatible con OpenAI; por defecto, Gemini. |

## IA local del equipo (modelo propio en el servidor)

- **Modelo:** Gemma 3 1B (`unsloth/gemma-3-1b-it`) ajustado con LoRA en Colab con datos del
  proyecto (`training/`), exportado a GGUF Q4_K_M (0,8 GB).
- **Dataset v2 (asesor):** 1513 ejemplos de entrenamiento y 131 de evaluación; agrega revisiones
  con propuesta, multiplicidades en el prompt y corrige la dirección de agregación/composición.
- **Servidor:** llama.cpp en una EC2 aparte (`deploy/model_server`), accesible solo desde el
  backend y con clave; se actualiza solo cuando se publica un modelo nuevo desde Colab.
- **Enlace cifrado:** las dos EC2 están en cuentas de AWS distintas y se hablan por IP pública,
  así que el modelo sirve **solo HTTPS** con un certificado propio y el backend confía únicamente
  en ese certificado (*pinning*, `LOCAL_MODEL_CERT`); pruebas `tests/test_modelo_tls.py` (3).
- **Backend:** proveedor `trained` (`services/trained_model.py`) con el **mismo prompt del
  entrenamiento** (`training/prompt_contract.py`): ejecuta las ediciones y deja como propuesta
  lo que recomienda como asesor.
- **Medido** con el modelo v2 en 2 CPU desde producción: edición 8 s, mentoría 11 s, revisión
  con propuesta 37 s (la más larga: escribe varias operaciones); pruebas
  `tests/test_modelo_propio.py` (7).
- **Evaluación v2** (131 ejemplos que el modelo no vio; base → entrenado): JSON válido 88,8 →
  97,5 %; herramientas correctas 25 → 95 %; se dirige por el nombre 30 → 97,5 %; mentoría sin
  acciones 12,5 → 100 %; revisión con la propuesta correcta 21,4 → 92,9 %.
- El mismo modelo corre también en el celular (primer parcial), que ahora también deja
  propuestas como asesor.

## Limitaciones conocidas

- Las propuestas se aceptan desde la **web**. En la app móvil se ve la respuesta del asesor, pero
  no la tarjeta con los botones.
- El uso del proveedor se registra en el log (modelo, modo, duración); el SDK de Gemini usado no
  expone tokens/costo por consulta, así que no se registran.
- Si al aplicar una propuesta falla una operación a mitad de camino, las anteriores quedan
  aplicadas (cada operación usa el servicio del primer parcial, que confirma una por una) y la
  propuesta queda “falló al aplicarse” con el detalle. La validación previa hace que sea raro.

## Cómo reproducir

```bash
docker volume create parcial_sw_test_pgdata
PG_VOLUME_NAME=parcial_sw_test_pgdata GEMINI_API_KEY=... docker compose up -d --build
docker cp backend/tests/. uml-diagramador-backend:/app/tests
docker cp exporters/tests/. uml-diagramador-backend:/app/exporters/tests
docker exec -e RUN_GEMINI_TESTS=1 -w /app uml-diagramador-backend python -m pytest tests exporters/tests
```

Las pruebas del asesor (`backend/tests/test_asesor_2p.py`) usan un modelo falso compatible con
OpenAI y no requieren clave. La demostración con 3 sesiones: crear el diagrama, compartirlo
(ícono 👥), y desde el chat preguntar “@IA ¿Cómo relacionamos Cliente y Pedido?”; la respuesta
llega dirigida a quien preguntó con una propuesta que esa persona (o el dueño) aplica con
**Aplicar**.

## Pendiente

1. Redesplegar la **web** en producción: la desplegada es anterior a la opción *Modelo propio del
   equipo* en la configuración de la IA (el resto del 2P sí está desplegado).
2. Redesplegar el **backend** con el arreglo de “borrar el diagrama mientras la IA responde”.

Hecho: EC2 del modelo conectada por HTTPS con pinning, modelo v2 entrenado y publicado, APK
nueva instalada (prompt v2, propuestas del asesor y cierre de sesión al vencer el token).
