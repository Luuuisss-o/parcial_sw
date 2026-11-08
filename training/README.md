# Modelo de IA personalizado del equipo (Fase 2, CU-17)

Un modelo chico (**Gemma 3 1B IT**) entrenado con **LoRA** para actuar como el integrante IA
del equipo en el chat del diagrama, exportado a **GGUF** y ejecutado **localmente en el
celular** (llama.cpp vía `llamadart`). El servidor solo **aloja** el archivo; la inferencia
corre en el teléfono.

```
build_dataset.py ──► data/train.jsonl ──► finetune_colab.ipynb (GPU T4) ──► .gguf
       ▲                                                                     │
       │ prompt (único)                                PUT /models/assistant  ▼
mobile/lib/services/assistant_prompt.dart            backend (solo aloja el archivo)
                                                                             │
                                          GET /models/assistant/download     ▼
                                       celular: descarga + SHA-256 + llama.cpp local
```

## Qué aprende el modelo (personalización)

| Comportamiento | Fuente de los ejemplos |
|---|---|
| Formato exacto de la app: `{"say": ..., "actions": [...]}` con las 9 herramientas del diagramador | Plantillas (`build_dataset.py`) |
| Dirigirse a quien pregunta por su nombre de pila | Todas las respuestas |
| Mentoría de diseño (UML, requerimientos, patrones, SOLID, PUDS…) sin tocar el diagrama | **Destilación**: 129 preguntas respondidas por Gemini (`data/teacher_mentor.jsonl`) |
| Resolver referencias con el hilo propio ("y ponele isbn" → la clase de *su* consulta, no la del compañero) | Plantillas con historial y contexto del equipo |
| Entrega de soluciones según la configuración del diagrama: rechazar (desactivada) o diseñar 3-6 clases (activada) | 20 sistemas diseñados por Gemini (`data/teacher_solutions.jsonl`) |

Dataset actual: **1274 ejemplos de entrenamiento / 110 de evaluación** (788 ediciones,
556 mentoría, 40 soluciones completas), ~800 tokens de mediana y 1700 de máximo: entra holgado
en los 4096 tokens de contexto que usa el celular.

## Un solo prompt para entrenar y para usar

Si el prompt del celular no coincide con el del entrenamiento, el modelo pierde casi todo lo
aprendido. Por eso:

- El prompt de sistema vive **solo** en `mobile/lib/services/assistant_prompt.dart`;
  `prompt_contract.py` lo lee de ahí.
- El armado del mensaje (contexto híbrido) está en Dart y en Python, y los dos se verifican
  contra la misma referencia `fixtures/context_example.expected.txt`
  (`tests/test_prompt_contract.py` y `mobile/test/services/assistant_prompt_test.dart`).

## Reproducir

```bash
cd training
python build_dataset.py              # arma data/train.jsonl y data/eval.jsonl
python -m pytest tests -q            # invariantes del dataset y del contrato
```

Para regenerar las respuestas del modelo maestro (opcional; ya están versionadas en `data/`):

```bash
GEMINI_API_KEY=... python build_dataset.py --teacher
```

Si se agota la cuota diaria de `gemini-3.5-flash`, sigue solo con `gemini-3.5-flash-lite`.

## Entrenar en Google Colab

1. Abrir `finetune_colab.ipynb` en Colab → *Entorno de ejecución → GPU T4*.
2. Ejecutar todo. El notebook:
   - mide el **modelo base** sobre `eval.jsonl` (JSON válido, herramientas correctas, nombre,
     mentoría sin acciones);
   - entrena con LoRA (r=16, 2 épocas, solo sobre la respuesta), ~15-25 min;
   - mide el **modelo personalizado** con las mismas métricas (para comparar);
   - exporta a GGUF (Q4_K_M ≈ 0.8 GB, o Q8_0 si la versión de Unsloth no lo soporta);
   - lo publica en el backend (`PUT /models/assistant`, usuario con rol `admin`).
3. El progreso queda en Google Drive (`MyDrive/uml_ia/`): línea de base, checkpoints cada 40
   pasos, modelo entrenado y `.gguf`. Si Colab se desconecta, se vuelve a ejecutar todo en orden y
   cada paso ya hecho se salta o se retoma desde el último checkpoint.
4. (Opcional) La última sección lo sirve desde Colab como API compatible con OpenAI, para que
   la web también lo pueda elegir como proveedor (chat → *Modelo* → *Cambiar* → *Colab / vLLM*).

## En el celular

Chat del diagrama (botón 💬) → interruptor *"IA en este celular"*. Al abrirlo, la app consulta
`GET /models/assistant`; si hay una versión nueva la descarga (retoma descargas cortadas),
verifica el SHA-256 y la carga. Sin modelo personalizado en el servidor, usa el modelo base
empaquetado en el APK; sin red, el último descargado.

Una consulta `@IA` del usuario se marca `answer_on_device`: el servidor **no** llama a ningún
modelo; el celular pide el contexto híbrido (`GET /diagrams/{id}/chat/{q}/context`), genera la
respuesta, aplica las acciones por la API REST normal y la publica
(`POST /diagrams/{id}/chat/{q}/answer`), dirigida a quien preguntó y visible para todo el equipo,
con el nombre del modelo que la generó.

## Limitaciones (honestas)

- Este entorno de desarrollo no tiene GPU ni acceso a Hugging Face: **el entrenamiento no se
  ejecutó acá**. El notebook está validado sintácticamente y el dataset con tests, pero las
  métricas reales salen al correrlo en Colab.
- Un modelo de 1B es chico: el docente advierte que "un modelo simple no se va a poder". La
  personalización compensa en el formato y los comportamientos del chat, pero las respuestas
  de mentoría van a ser más cortas y menos precisas que las de Gemini. Para la web conviene un
  modelo más grande servido desde Colab u Ollama (CU-17).
