# Importar desde una foto e intercambiar con Enterprise Architect

Revisado el 2026-11-11.

## Desde una foto o captura (IA)

Se usa desde **Mis diagramas**, con el botón "Importar desde foto" en la web
y el ícono de cámara en la app Android. Se puede sacar la foto o elegirla de
la galería.

1. La IA (Gemini) lee la imagen y decide qué tipo de diagrama es.
2. Se muestra lo que leyó, **sin crear nada todavía**. Se puede destildar lo
   que no corresponda y corregir nombres (las relaciones siguen al nombre
   corregido).
3. Al confirmar, se crea un diagrama nuevo y se abre.

| Imagen | Qué se obtiene |
|---|---|
| Diagrama de clases UML (pizarra, papel, captura o export de otra herramienta) | Clases, interfaces, enumeraciones y abstractas. Atributos con visibilidad, estático, derivado, multiplicidad y valor inicial. Métodos con parámetros. Asociación, agregación, composición, herencia, realización y dependencia, con multiplicidad, roles y navegabilidad |
| Diagrama de base de datos: pata de gallo (crow's foot), Chen, IDEF1X o modelo relacional de Workbench, pgAdmin, DBeaver… | Cada tabla es una clase y cada columna, un atributo con tipo traducido (`BIGINT`→long, `NUMERIC`→decimal, `TIMESTAMP`→datetime…). La PK y las columnas `NOT NULL` quedan obligatorias. Cada FK es una asociación con la multiplicidad de la notación; la columna FK no se copia como atributo, porque el backend generado la crea a partir de la relación |

Probado con Gemini real usando dos imágenes generadas para la prueba:

- **Base de datos:** 4 tablas en pata de gallo. Las multiplicidades `0..*`,
  `1..*` y `1` salieron exactas, igual que los tipos y las PK.
- **UML 2.5:** interfaz, clase abstracta, enumeración, estáticos, derivados,
  realización, herencia y composición con su rol. Todo salió correcto.

Las pruebas automáticas (`tests/unit/test_vision_parse.py` y
`test_uml25.py::test_import_desde_foto...`) no llaman a Gemini: verifican
cómo se interpreta su respuesta y la creación del diagrama.

## Enterprise Architect (XMI 2.1)

En el editor, con los botones de exportar e importar XMI de la barra
superior.

- **Exportar:** genera un XMI 2.1 con el formato que entiende EA. Se verificó
  abriéndolo en EA 17.2: sentido de las asociaciones, rombos en la clase
  correcta y tipos `Date`/`Double`/`Long` como DataType. Incluye la notación
  UML 2.5: `uml:Interface`, `uml:Enumeration`, `interfaceRealization`,
  visibilidad, `isStatic`, `isDerived`, parámetros, roles y
  `navigableOwnedEnd`.
- **Importar:**
  - **Diagramas de clases:** se probó con archivos reales exportados por EA
    17.2 (`tests/fixtures/xmi/ea_*.xmi`). Toma los tipos de la extensión de
    EA, las clases de asociación y la dirección de los conectores.
  - **Modelos de datos de EA:** tablas «table», columnas «column» y
    restricciones «PK»/«FK»/«index», que EA guarda como operaciones y por eso
    no se importan como métodos. La PK queda obligatoria, la columna FK se
    reemplaza por la relación y los tipos SQL se traducen. Se probó con un
    archivo **escrito a mano con el formato de EA**
    (`ea_modelo_datos.xmi`): falta confirmarlo con un export real de un
    modelo de datos.
- **Ida y vuelta:** exportar e importar en un diagrama vacío conserva todo
  (`test_xmi_roundtrip.py`, `test_uml25.py`).
