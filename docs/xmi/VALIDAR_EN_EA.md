# Validar el XMI en Enterprise Architect (CU-06)

Validado el 9/11/2026 con Enterprise Architect 17.2 (de forma automatizada, por su interfaz
COM): todos los puntos de abajo dieron bien en las dos direcciones. `exportado-desde-ea.xmi` es
el archivo que exportó EA en esa prueba. Esta guía queda para repetir la verificación a mano
(toma unos 5 minutos).

## A. Del editor a EA

1. En EA: crear un proyecto vacío (o abrir `docs/Diagramas/Proyecto_SW.qea.eapx`) y seleccionar
   un paquete en el *Project Browser*.
2. **Publish → Import/Export → Import Package from XMI** y elegir
   `docs/xmi/ejemplo-completo.xmi` (exportado por el editor, formato XMI 2.1).
3. Verificar en el paquete importado:
   - [ ] 10 clases: Persona, Cliente, Empleado, Pedido, DetallePedido, Producto, Categoria,
         Proveedor, Direccion, Factura.
   - [ ] Atributos con su tipo (ej. `Pedido.fecha: Date`, `Pedido.total: BigDecimal`,
         `Empleado.sueldo: Double`, `Producto.codigo: Long`, `Factura.emitida: LocalDateTime`).
   - [ ] Herencia: `Cliente` y `Empleado` generalizan a `Persona`.
   - [ ] Una composición (rombo lleno en `Pedido`) y una agregación (rombo vacío en `Proveedor`).
   - [ ] La asociación recursiva de `Categoria` consigo misma.
   - [ ] Multiplicidades en los extremos (ej. `1` y `0..*` entre Cliente y Pedido).
4. Para ver las clases dibujadas: arrastrarlas a un diagrama de clases nuevo (el XMI trae el
   modelo, no la disposición gráfica).

## B. De EA al editor

1. En EA, seleccionar el paquete y **Publish → Import/Export → Export Package to XMI**, con
   *XMI Type* = **UML 2.1 (XMI 2.1)**.
2. En el editor web: crear un diagrama vacío, abrirlo y, en la barra de arriba, tocar el ícono
   de **subir** ("Importar un diagrama desde un archivo .xmi") y elegir ese archivo.
3. Verificar que aparecen las mismas clases, atributos, herencias, composición/agregación y
   multiplicidades. El resumen de la importación indica lo creado y lo que se omitió
   (`warnings`): anotá cualquier advertencia.

## Si algo no coincide

Guardá el archivo exportado por EA en `docs/xmi/` y anotá qué elemento falta o cambió: con ese
archivo real se puede agregar una prueba automática al importador (`backend/app/services/xmi.py`).
