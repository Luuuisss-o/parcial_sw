# Diagramas de Comunicación — parcial_sw

13 diagramas de comunicación en formato **PlantUML**, uno por caso de uso, derivados del código real del proyecto.

## Archivos

| CU | Archivo | Descripción |
|---|---|---|
| CU-01 | `CU01_Iniciar_Sesion.puml` | Login con JWT: Frontend → AuthRouter → PostgreSQL → localStorage |
| CU-02 | `CU02_Gestionar_Diagramas.puml` | CRUD de diagramas con filtro owner/collaborator |
| CU-03 | `CU03_Gestionar_Colaboradores.puml` | Agregar/listar/quitar colaboradores (solo dueño) |
| CU-04 | `CU04_Gestionar_Clases.puml` | CRUD de clases con broadcast WebSocket a otros clientes |
| CU-05 | `CU05_Gestionar_Atributos.puml` | CRUD de atributos con constraint UNIQUE(clase_id, nombre) |
| CU-06 | `CU06_Gestionar_Metodos.puml` | CRUD de métodos con constraint UNIQUE(clase_id, nombre) |
| CU-07 | `CU07_Gestionar_Relaciones.puml` | CRUD de relaciones: tipos, multiplicidad, anclajes |
| CU-08 | `CU08_Asistente_IA.puml` | Flujo completo texto+voz → Gemini → tool execution → WebSocket |
| CU-09 | `CU09_Importar_Foto.puml` | Detect (Gemini Vision) → revisión humana → Apply (2 pasos) |
| CU-10 | `CU10_Exportar_Importar_XMI.puml` | Export/Import XMI 2.1 compatible con Enterprise Architect |
| CU-11 | `CU11_Generar_Backend_SpringBoot.puml` | Pipeline completo: normalización → generadores → ZIP descargable |
| CU-12 | `CU12_Colaborar_Tiempo_Real.puml` | WebSocket: locks por clase, cursores en vivo, desconexión limpia |
| CU-13 | `CU13_Convertir_Clase_Asociacion.puml` | M:N → clase intermedia + 2 relaciones 1:N + eliminar original |

## Cómo importar en Enterprise Architect

### Opción 1: PlantUML directo (EA 16+)
EA 16+ tiene soporte nativo para PlantUML: `Specialize → Technologies → PlantUML`.

### Opción 2: Renderizar y recrear
1. Renderizá los `.puml` con [PlantUML Online](https://www.plantuml.com/plantuml/uml/) o la extensión de VS Code
2. Usá las imágenes como referencia para recrear en EA

### Opción 3: Usar el MCPAddin de EA desde Claude Desktop
Si tenés Claude Desktop con el MCPAddin de EA configurado, podés pasarle el contenido de cada `.puml` y pedirle que lo cree directamente en tu proyecto `Proyecto_SW.qea.eapx`.

## Notas técnicas

- Cada mensaje tiene **numeración jerárquica** (1, 1.1, 1.2...) que refleja la secuencia real de llamadas.
- Los objetos representan las **clases/componentes reales** del código (routers, services, hooks, stores, modelos ORM).
- Los flujos están verificados contra el código fuente: endpoints, parámetros, y respuestas son los reales.
- CU-08 y CU-12 son los más complejos por involucrar comunicación asíncrona (BackgroundTasks, WebSocket).
