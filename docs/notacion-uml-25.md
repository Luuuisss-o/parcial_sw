# Notación UML 2.5 del diagrama de clases

Qué parte de la notación de UML 2.5 soporta el editor, cómo se ve y hasta dónde
llega. Revisado el 2026-11-11.

## Lo que se soporta

| Elemento UML 2.5 | Cómo se dibuja | Web | Móvil | XMI | Generador |
|---|---|---|---|---|---|
| Clase | Caja con nombre, atributos y métodos | ✅ | ✅ | ✅ | Entidad JPA |
| Clase abstracta | Nombre en *cursiva* | ✅ | ✅ | `isAbstract="true"` | Entidad JPA |
| Interfaz | «interface» sobre el nombre | ✅ | ✅ | `uml:Interface` | No genera tabla |
| Enumeración | «enumeration» y compartimento de literales | ✅ | ✅ | `uml:Enumeration` + `ownedLiteral` | No genera tabla; un atributo de ese tipo se guarda como texto |
| Visibilidad | `+` público, `-` privado, `#` protegido, `~` paquete | ✅ | ✅ | `visibility` | — |
| Atributo | `vis /nombre : tipo [mult] = valor` | ✅ | ✅ | `ownedAttribute` | Columna |
| Atributo estático | Subrayado | ✅ | ✅ | `isStatic` | No es columna |
| Atributo derivado | `/` delante del nombre | ✅ | ✅ | `isDerived` | No es columna |
| Multiplicidad de atributo | `[0..1]`, `[1..*]`, `[*]` | ✅ | ✅ | `lowerValue` / `upperValue` | — |
| Valor inicial | `= valor` | ✅ | ✅ | `defaultValue` | — |
| Operación | `vis nombre(parámetros) : tipo` | ✅ | ✅ | `ownedOperation` + `ownedParameter` | — |
| Operación estática | Subrayada | ✅ | ✅ | `isStatic` | — |
| Operación abstracta | *Cursiva* | ✅ | ✅ | `isAbstract` | — |
| Asociación | Línea continua | ✅ | ✅ | `uml:Association` | `@OneToMany` / `@ManyToOne` / … |
| Agregación | Rombo hueco en el todo | ✅ | ✅ | `aggregation="shared"` | ✅ |
| Composición | Rombo lleno en el todo | ✅ | ✅ | `aggregation="composite"` | ✅ |
| Generalización (herencia) | Triángulo hueco hacia el padre | ✅ | ✅ | `generalization` | `extends` |
| Realización | Punteada con triángulo hueco hacia la interfaz | ✅ | ✅ | `interfaceRealization` | Se ignora (no es tabla) |
| Dependencia | Punteada con flecha **abierta** | ✅ | ✅ | `uml:Dependency` | ✅ |
| Multiplicidad de extremo | `1`, `0..1`, `*`, `1..*` | ✅ | — | ✅ | ✅ |
| Nombre de rol | En cursiva junto al extremo | ✅ | ✅ | `name` del `ownedEnd` | — |
| Navegabilidad | Flecha abierta en el extremo navegable | ✅ | ✅ | `navigableOwnedEnd` | — |
| Nombre de la asociación | Sobre la línea | ✅ | — | `name` | — |
| Clase de asociación | Clase unida con línea punteada | ✅ | — | `uml:AssociationClass` | Tabla intermedia |

La ida y vuelta por XMI (exportar e importar en un diagrama vacío) conserva
todo lo de la tabla. Lo verifica `backend/tests/test_uml25.py`.

## Lo que no se soporta

Estos elementos son parte de UML 2.5, pero no del diagrama de clases que
pide la materia, y ninguno se traduce al backend generado:

- Paquetes y diagramas de paquetes.
- Notas y restricciones en OCL o entre llaves (`{ordered}`, `{unique}`).
- Clases parametrizadas (templates).
- Asociaciones n-arias (de tres o más clases) y asociaciones calificadas.
- Puertos, partes y estructura compuesta.
- Estereotipos libres, fuera de «interface» y «enumeration».

## Compatibilidad

- **Diagramas existentes:** se ven igual que antes, con dos excepciones. Ahora
  se muestra la visibilidad (`-` en los atributos y `+` en los métodos, la
  convención habitual). Y la multiplicidad `1..1` se abrevia a `1`, y `0..*`
  a `*`, como indica UML.
- **Asistente de IA:** el esquema de herramientas que ve no cambió, para no
  romper el contrato con el modelo propio entrenado. Puede crear realizaciones
  (el tipo `REALIZATION` es válido), pero el resto de la notación nueva se
  edita desde el editor o se importa por XMI.
- **Migración:** `a3c5e7f9b1d2_notacion_uml_25`. Agrega columnas y no borra
  nada; todas las columnas nuevas tienen un valor por defecto.
