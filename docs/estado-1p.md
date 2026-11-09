# Estado del primer parcial (CU-01 … CU-09)

Auditoría del repositorio contra `PLAN_DESARROLLO_1P.md`, hecha el 9/11/2026 sobre la rama
`claude/exciting-tesla-sscl8u`. Cada estado se respalda con una prueba **ejecutada**, no con
revisión de código. Lo que no se pudo ejecutar figura como **PENDIENTE**.

## Resumen

| ID | Caso de uso | Estado | Evidencia |
|---|---|---|---|
| CU-01 | Crear/abrir y compartir un diagrama | **COMPLETA** | Prueba de 3 usuarios contra producción (dueña + 2 colaboradores); prueba manual con 3 personas reales |
| CU-02 | Diseñar clases UML manualmente | **COMPLETA** | `backend/tests/test_api_qa.py` (CRUD de clases, atributos, métodos, relaciones, multiplicidades) |
| CU-03 | Edición colaborativa en tiempo real | **COMPLETA** | Prueba de 3 usuarios (21/21); exclusión mutua por clase; navegador real: pestaña quieta >100 s y reconexión (5/5) |
| CU-04 | IA de edición por texto y voz | **COMPLETA** | Gemini real (`RUN_GEMINI_TESTS=1`); confirmación de eliminaciones (`test_ai_confirmacion.py`); voz en el celular probada en un Samsung A34 |
| CU-05 | Foto → diagrama | **COMPLETA** (ver limitación) | Imagen de un diagrama → Gemini Vision → vista previa → diagrama con 2 clases, 4 atributos y la relación |
| CU-06 | Importar/exportar XMI (Enterprise Architect) | **PARCIAL** — falta abrirlo en EA | Ida y vuelta automática sin pérdida (`test_xmi_roundtrip.py`); **PENDIENTE**: validar en Enterprise Architect |
| CU-07 | Generar backend Spring Boot + PostgreSQL | **COMPLETA** | Proyecto generado → Maven → Docker con PostgreSQL → CRUD real 25/25 y diagrama con todos los tipos de relación |
| CU-08 | App móvil por voz contra el backend generado | **COMPLETA** | Protocolo UAP del backend generado (alta/consulta); pantallas de voz del celular |
| CU-09 | IA local en el celular, offline y sincronización | **COMPLETA** | Modelo propio en el teléfono (25–51 s/respuesta); alta reenviada sin duplicar, también tras reiniciar el backend |

## Detalle por caso de uso

### CU-01 / CU-02 — Diagramas compartidos y edición manual
- Código: `backend/app/routers/{diagramas,classes,atributos,metodo,relacion}.py`, `frontend/src/pages/Diagram.jsx`.
- Compartir: el dueño agrega colaboradores por email (ícono 👥 del editor, `POST /diagrams/{id}/collaborators`).
- Pruebas: `backend/tests/test_api_qa.py`.

### CU-03 — Tiempo real
- Canal WebSocket por diagrama (`backend/app/routers/realtime.py`); exclusión mutua por clase (`services/locks.py`): si alguien edita una clase, el resto no puede tomarla hasta que la libere (no hay "gana el último" silencioso).
- **Corregido en esta auditoría:** nginx corta el WebSocket a los 100 s sin tráfico y la web no se reconectaba: una pestaña quieta dejaba de recibir cambios sin avisar. Ahora la web y el celular mandan `ping` cada 25 s (el servidor responde `pong`) y, si la conexión cae, se reconectan con espera creciente y recargan clases, relaciones y chat.
- Pruebas: `test_cn_ws_00*` (incluye `ping`/`pong`), prueba de 3 usuarios simultáneos, prueba en Chrome real (pestaña quieta 130 s y reinicio del backend).

### CU-04 — IA de edición
- Flujo: texto/voz → modelo → herramientas tipadas (`services/ai_tools.py`) → validación → servicio de operaciones → evento WebSocket. El modelo nunca ejecuta código ni escribe en la base directamente.
- Voz en la web (`hooks/useVoiceRecorder.js` → `/voice`) y en el celular (Vosk offline).
- **Agregado en esta auditoría:** confirmación de acciones destructivas, como regla del servidor (no del criterio del modelo): borrar una clase con atributos/métodos/relaciones o varias cosas a la vez requiere que el usuario confirme ("@IA confirmo, eliminá Cliente"). La misma regla corre en la IA del celular.
- **Corregido:** si el modelo prometía un cambio sin ejecutarlo, ahora se reintenta y, si no, se responde honestamente; la herramienta `create_relation` documenta la dirección (herencia: hija→padre; composición: parte→todo).

### CU-05 — Foto → diagrama
- `POST /vision/detect` (Gemini Vision) → vista previa editable en la web → `POST /vision/apply`. Nunca escribe sin revisión humana.
- **Corregido:** una imagen que Gemini no puede procesar devolvía 502 ("falla del servidor"); ahora 422 con un mensaje claro.
- Limitación: la lectura de multiplicidades depende del modelo (en una prueba leyó `1..*` donde el dibujo decía `*`); para eso está la vista previa editable.

### CU-06 — XMI
- `services/xmi.py`: XMI 2.1, perfil UML 2.1, identificadores estables por id de la base, `generalization` para herencia y `ownedEnd` con `aggregation` para composición/agregación.
- **Corregido:** `Double`, `decimal` y `Long` se exportaban como el primitivo genérico `Real`/`Integer` y volvían como `float`/`int` (el backend generado perdía precisión). Ahora viajan como `uml:DataType` propios. Lo mismo para el tipo de retorno de los métodos.
- Prueba automática: ida y vuelta (exportar → importar en un diagrama vacío) conserva clases, atributos con su tipo, herencia, composición y multiplicidades.
- **PENDIENTE:** abrir el XMI exportado en Enterprise Architect (`Publish → Import/Export Package from XMI`) e importar un XMI exportado por EA. No hay EA en este entorno. Hay un proyecto EA en `docs/Diagramas/Proyecto_SW.qea.eapx` para hacerlo.

### CU-07 — Backend generado
Pipeline: `exporters/generators/project_builder.py` → entidades JPA (`json_to_full_orm.py`), repositorios, **capa de API** (`api_layer.py`: DTO + Service + Controller + manejo de errores), protocolo UAP, Postman, Docker.

**Bugs reales encontrados al compilar y probar el proyecto generado, y corregidos:**

| Problema | Efecto | Corrección |
|---|---|---|
| `ObjectMapper` propio que reemplazaba al de Spring | crear algo con fecha → 500; `GET /{id}` devolvía `{"present":true}` | customizer que conserva los módulos de Spring |
| Relaciones sin getters/setters | no se podía asignar `Pedido.cliente` | accesores generados (`@JsonIgnore` en la entidad) |
| Controlador exponía la entidad | sin DTO, recursión, 200 vacío si no existe | DTO con relaciones como ids; 201/204/404/400/409 |
| `ddl-auto=create` | **borraba la base en cada reinicio** | `update` (configurable con `DDL_AUTO`) |
| Credenciales fijas en el código | — | variables de entorno (`DB_USER`, `DB_PASSWORD`, …) |
| `@OneToMany(mappedBy=…, mappedBy=…)` | relaciones "muchos → uno" no compilaban | anotación sin duplicar |
| Postman con campos inexistentes | los ejemplos no funcionaban | cuerpos = DTO real |

Prueba E2E (Cliente/Pedido/Producto): compila con Maven, levanta con PostgreSQL y pasa 25/25 verificaciones (alta, lectura, modificación y baja con relaciones; 400/404/409; datos que sobreviven a un reinicio). Además, un diagrama de 10 clases con herencia, composición, agregación, dependencia, uno a uno, muchos a muchos y una relación recursiva **compila, arranca y responde CRUD**.

Lo que el generador no hace: reglas de negocio que el diagrama no expresa (cálculos, estados, permisos) — se programan en `services/`, como indica el README generado.

### CU-08 / CU-09 — Móvil, IA local y offline
- App Flutter (`mobile/`), compilada e instalada en un teléfono físico (Samsung A34, Android 16).
- IA en el teléfono: Gemma 3 1B ajustado con LoRA (`training/`), GGUF de 0,8 GB que el celular descarga del servidor y verifica por SHA-256. Métricas sobre 110 ejemplos de evaluación: JSON válido 46,7 % → 100 %, uso de herramientas 55 % → 100 %, respuesta por nombre 16,7 % → 100 %, mentoría sin tocar el diagrama 90,9 % → 100 %. Tiempo de respuesta en el teléfono: 25–51 s.
- Voz offline: Vosk (español). Corregido el cierre de la app en release (R8 renombraba las clases de JNA).
- Backend generado: protocolo UAP (`/uap/v1/manifest|tools|sync`) que la app descubre en tiempo de ejecución; cola local de operaciones en SQLite (`mobile/lib/uap/`).
- **Corregido:** la idempotencia del alta desde el celular (`clientRecordId`) vivía en memoria: si el backend generado se reiniciaba y el celular reenviaba una operación pendiente, se duplicaba. Ahora se guarda en `uap_change_log` (columna única) y sobrevive al reinicio (probado).

## Seguridad corregida en esta auditoría
- `POST /diagrams/{id}/export-download` no exigía sesión: cualquiera con el id de un diagrama descargaba su backend generado. Ahora exige sesión y acceso al diagrama.

## Cómo reproducir las pruebas

```bash
# Stack local con una base de prueba aislada
docker volume create parcial_sw_test_pgdata
PG_VOLUME_NAME=parcial_sw_test_pgdata docker compose up -d --build

# Backend + generador (dentro del contenedor; requiere el usuario qa.tester, ver tests/test_api_qa.py)
docker cp backend/tests uml-diagramador-backend:/app/tests
docker cp exporters/tests/. uml-diagramador-backend:/app/exporters/tests
docker exec -w /app uml-diagramador-backend python -m pytest tests exporters/tests
# Con una GEMINI_API_KEY válida en el backend, sumar las pruebas que llaman a Gemini:
docker exec -e RUN_GEMINI_TESTS=1 -w /app uml-diagramador-backend python -m pytest tests

# Móvil
cd mobile && flutter test
flutter test test/integration --dart-define=API_BASE_URL=http://127.0.0.1:8000   # con el seed demo cargado
```

Resultado al cerrar esta auditoría: backend 101/101 (con Gemini real), generador 88/88, móvil 133/133
(incluidas 3 de integración contra el backend), web compila sin errores.

## Pendientes
1. **Validar el XMI en Enterprise Architect** (CU-06), en las dos direcciones.
2. Desplegar en el servidor de producción los cambios de esta auditoría (backend y web).
3. Generar e instalar el APK con la regla de confirmación de eliminaciones en el celular.
