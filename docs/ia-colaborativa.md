# La IA como un desarrollador más del equipo

Cómo atiende la IA a varios desarrolladores que trabajan a la vez sobre el
mismo diagrama. Revisado el 2026-11-11.

## Qué hace

| Necesidad | Cómo se resuelve | Dónde |
|---|---|---|
| Varios preguntan a la vez | Cada consulta corre en su propio hilo, sin esperar a las de los demás | `chat_service.run_ai_question_background` (BackgroundTask) |
| Que nadie acapare a la IA | Una consulta pendiente por persona y diagrama | `chat_service.question_in_progress` |
| Responderle a cada uno | La respuesta nombra a quien preguntó y cita su mensaje; la ve todo el equipo | `address_reply`, `reply_to_id` |
| Contexto de cada uno | Usa el historial de esa persona con la IA y lo último que habló el equipo | `user_ai_history`, `team_context` |
| Ver qué está haciendo | El estado "pensando para Ana" y cada edición llegan en vivo a todos | `notify_ai_started` y eventos de clase y relación |
| Que dos pedidos simultáneos no se pisen | Las ediciones de la IA sobre un mismo diagrama se ejecutan de a una (un lock por diagrama); diagramas distintos no se esperan | `ai_tools.diagram_edit_lock` |
| Respetar al que está editando | La IA no toca una clase que otro integrante tiene tomada en el editor; la de quien pidió el cambio, sí | `DiagramToolExecutor._guard_human_lock` |
| Aceptar una propuesta sin carreras | Revisar si quedó desactualizada y aplicarla se hace con el lock tomado | `ai_proposals.decide` |
| Varias consultas al modelo propio | 4 consultas en paralelo, cada una con su propio contexto de 4096 tokens | `deploy/model_server/docker-compose.yml` |
| IA en el celular | Cada celular responde las consultas de su dueño con su modelo local; la respuesta se publica para todos y sus propuestas pasan por la misma validación | `chat_service.save_device_answer` |

## Pruebas

`backend/tests/test_ia_colaborativa.py`:

- Tres integrantes preguntan a la vez y las tres consultas corren en
  paralelo. Cada respuesta va a quien preguntó.
- Seis pedidos de "creá Cliente" en el mismo instante dejan una sola clase.
  Sin el lock por diagrama quedaban **seis clases repetidas**.
- La IA no modifica una clase que otro integrante está editando.
- Renombrar una clase a un nombre que ya existe se rechaza.

## Límites

- **El modelo propio corre en CPU (2 núcleos).** Con varias consultas a la vez,
  cada una tarda más, porque se reparten el procesador. La espera máxima es de
  240 s.
- **El lock por diagrama vive en memoria.** Alcanza porque el backend corre en
  un solo proceso. Con varios procesos habría que llevarlo a la base o a Redis.
