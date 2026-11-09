// src/hooks/useClassesAndDetails.js
import { useEffect, useState } from "react";
import {
  listClasses,
  createClass as apiCreateClass,
  updateClass,
  deleteClass as apiDeleteClass,
  updateClassPosition,
  updateClassSize,
  listAttributes,
  listMethods,
  createAttribute,
  updateAttribute,
  deleteAttribute,
  createMethod,
  updateMethod,
  deleteMethod,
} from "../api/classes";
import useDebouncedCallback from "./useDebouncedCallback";
import { connect, disconnect, onEvent as subscribe } from "../api/realtime";
import useUndo from "../store/undo";

/** Devuelve "campo", "campo2", "campo3"… evitando los nombres ya usados. */
function nextFreeName(base, taken) {
  const usados = taken.map((t) => String(t).toLowerCase());
  if (!usados.includes(base)) return base;
  let i = 2;
  while (usados.includes(`${base}${i}`)) i++;
  return `${base}${i}`;
}

function normalizeAttr(a) {
  return {
    ...a,
    name: a.name ?? a.nombre,
    type: a.type ?? a.tipo,
    required: a.required ?? a.requerido,
  };
}

function normalizeMeth(m) {
  return {
    ...m,
    name: m.name ?? m.nombre,
    return_type: m.return_type ?? m.tipo_retorno,
  };
}

export default function useClassesAndDetails(diagram) {
  // 🔹 Lista de clases
  const [classes, setClasses] = useState([]);

  // 🔹 Clase seleccionada
  const [selectedId, setSelectedId] = useState(null);
  const selected = classes.find((c) => c.id === selectedId) || null;

  // 🔹 Cache de atributos/métodos por clase
  const [detailsByClass, setDetailsByClass] = useState({});

  // 🔹 Estados de inserción
  const [insertMode, setInsertMode] = useState(false);
  const [insertName, setInsertName] = useState("NuevaClase");

  // 🔹 Registro de acciones reversibles (Ctrl+Z)
  const pushUndo = useUndo((s) => s.push);

  // ====== CARGA DE DETALLES ======
  const fetchDetails = async (classId) => {
    if (!classId) return;
    try {
      const [a, m] = await Promise.all([listAttributes(classId), listMethods(classId)]);
      setDetailsByClass((prev) => ({ ...prev, [classId]: { attrs: a || [], meths: m || [] } }));
    } catch {
      setDetailsByClass((prev) => ({ ...prev, [classId]: { attrs: [], meths: [] } }));
    }
  };

  // ====== CARGA DE CLASES ======
  // refreshDetails: tras una reconexión del WebSocket hay que volver a pedir
  // atributos y métodos de TODAS las clases (pudieron cambiar mientras
  // estábamos desconectados), no solo los de las clases nuevas.
  async function loadClasses({ refreshDetails = false } = {}) {
    try {
      const items = await listClasses(diagram?.id);
      setClasses(items || []);
      if (selectedId && !items?.some((x) => x.id === selectedId)) setSelectedId(null);

      await Promise.all(
        (items || []).map((c) =>
          detailsByClass[c.id] && !refreshDetails ? Promise.resolve() : fetchDetails(c.id)
        )
      );
    } catch {
      setClasses([]);
      setSelectedId(null);
    }
  }

  // ====== Helpers ======
  function replaceDetails(classId, patch) {
    setDetailsByClass((prev) => ({
      ...prev,
      [classId]: { ...(prev[classId] || { attrs: [], meths: [] }), ...patch },
    }));
  }

  // ====== EFECTO PRINCIPAL ======
  useEffect(() => {
    if (diagram) {
      loadClasses();
      connect(diagram.id);

      // Los listeners persisten hasta que uno se da de baja, asi que hay que
      // guardar cada baja y ejecutarlas en el cleanup: si no, cada vez que
      // se re-ejecuta este efecto se acumulan duplicados y un mismo evento
      // entrante se aplicaria varias veces al estado.
      const offs = [];
      const onEvent = (event, cb) => offs.push(subscribe(event, cb));

      onEvent("reconnected", () => loadClasses({ refreshDetails: true }));

      onEvent("class.created", (c) => {
        // El que creó la clase también recibe su propio broadcast, así que
        // hay que ignorarla si ya está en la lista.
        setClasses((prev) => (prev.some((x) => x.id === c.id) ? prev : [...prev, c]));
        setDetailsByClass((prev) =>
          prev[c.id] ? prev : { ...prev, [c.id]: { attrs: [], meths: [] } }
        );
      });

      onEvent("class.updated", (c) => {
        const normalized = {
          ...c,
          name: c.name ?? c.nombre, // si viene "nombre", lo copiamos a "name"
        };
        setClasses((prev) =>
          prev.map((x) => (x.id === normalized.id ? { ...x, ...normalized } : x))
        );
      });

      onEvent("class.deleted", ({ id }) => {
        setClasses((prev) => prev.filter((x) => x.id !== id));
        setDetailsByClass((prev) => {
          const n = { ...prev };
          delete n[id];
          return n;
        });
        if (selectedId === id) setSelectedId(null);
      });

      // ====== Eventos de atributos ======
      onEvent("attribute.created", (a) => {
        const attr = normalizeAttr(a);
        setDetailsByClass((prev) => {
          const current = prev[attr.clase_id]?.attrs || [];
          if (current.some((x) => x.id === attr.id)) return prev; // ya lo teníamos
          return {
            ...prev,
            [attr.clase_id]: {
              ...(prev[attr.clase_id] || { attrs: [], meths: [] }),
              attrs: [...current, attr],
            },
          };
        });
      });

      onEvent("attribute.updated", (a) => {
        const attr = normalizeAttr(a);
        setDetailsByClass((prev) => {
          const next = (prev[attr.clase_id]?.attrs || []).map((x) =>
            x.id === attr.id ? attr : x
          );
          return {
            ...prev,
            [attr.clase_id]: {
              ...(prev[attr.clase_id] || { attrs: [], meths: [] }),
              attrs: next,
            },
          };
        });
      });

      onEvent("attribute.deleted", ({ id, clase_id }) => {
        setDetailsByClass((prev) => {
          const next = (prev[clase_id]?.attrs || []).filter((x) => x.id !== id);
          return {
            ...prev,
            [clase_id]: {
              ...(prev[clase_id] || { attrs: [], meths: [] }),
              attrs: next,
            },
          };
        });
      });

      // ====== Eventos de métodos ======
      onEvent("method.created", (m) => {
        const meth = normalizeMeth(m);
        setDetailsByClass((prev) => {
          const current = prev[meth.clase_id]?.meths || [];
          if (current.some((x) => x.id === meth.id)) return prev; // ya lo teníamos
          return {
            ...prev,
            [meth.clase_id]: {
              ...(prev[meth.clase_id] || { attrs: [], meths: [] }),
              meths: [...current, meth],
            },
          };
        });
      });

      onEvent("method.updated", (m) => {
        const meth = normalizeMeth(m);
        setDetailsByClass((prev) => {
          const next = (prev[meth.clase_id]?.meths || []).map((x) =>
            x.id === meth.id ? meth : x
          );
          return {
            ...prev,
            [meth.clase_id]: {
              ...(prev[meth.clase_id] || { attrs: [], meths: [] }),
              meths: next,
            },
          };
        });
      });

      onEvent("method.deleted", ({ id, clase_id }) => {
        setDetailsByClass((prev) => {
          const next = (prev[clase_id]?.meths || []).filter((x) => x.id !== id);
          return {
            ...prev,
            [clase_id]: {
              ...(prev[clase_id] || { attrs: [], meths: [] }),
              meths: next,
            },
          };
        });
      });

      return () => {
        offs.forEach((off) => off());
        disconnect();
      };
    }
    // Depende de diagram?.id (string estable), NO del objeto `diagram`
    // entero: useDiagram puede devolver un objeto nuevo con el mismo id
    // (p.ej. si React vuelve a montar el árbol, StrictMode incluido), y
    // con el objeto completo como dependencia eso reconectaba el
    // WebSocket en cada uno de esos remounts -- una pestaña que se
    // reconectaba seguido perdía cualquier mensaje que llegara justo en
    // la ventana muerta entre cerrar y reabrir, incluidos los cursores en
    // vivo de otro colaborador.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagram?.id]);

  // ====== EFECTO: cargar detalles al seleccionar ======
  useEffect(() => {
    if (selectedId && !detailsByClass[selectedId]) {
      fetchDetails(selectedId);
    }
  }, [selectedId, detailsByClass]);

  // ====== Crear clase ======
  async function handleCanvasClick({ x_grid, y_grid }) {
    if (!insertMode) return;
    try {
      const c = await apiCreateClass(diagram.id, {
        name: insertName.trim() || "NuevaClase",
        x_grid, y_grid, w_grid: 12, h_grid: 6, z_index: 1,
      });
      await loadClasses();
      setSelectedId(c.id);
      replaceDetails(c.id, { attrs: [], meths: [] });

      pushUndo(`crear la clase ${c.name ?? c.nombre}`, async () => {
        await apiDeleteClass(c.id);
        setClasses((prev) => prev.filter((x) => x.id !== c.id));
        setSelectedId((cur) => (cur === c.id ? null : cur));
      });
    } catch (e) {
      alert(e?.response?.data?.detail || "No se pudo crear la clase");
    } finally {
      setInsertMode(false);
    }
  }

  // ====== RENAME ======
  const debouncedSave = useDebouncedCallback(async (classId, name) => {
    const updated = await updateClass(classId, { name });
    setClasses((prev) => prev.map((c) => (c.id === classId ? updated : c)));
  }, 600);

  async function handleRename(classId, name) {
    try {
      const updated = await updateClass(classId, { name });
      setClasses((prev) => prev.map((c) => (c.id === classId ? updated : c)));
    } catch (e) {
      alert(e?.response?.data?.detail || "No se pudo renombrar la clase");
    }
  }

  // ====== DRAG/RESIZE ======
  async function handleDragEnd(classId, { x_grid, y_grid }) {
    const antes = classes.find((c) => c.id === classId);
    try {
      await updateClassPosition(classId, { x_grid, y_grid });
      setClasses((prev) => prev.map((c) => (c.id === classId ? { ...c, x_grid, y_grid } : c)));

      if (antes && (antes.x_grid !== x_grid || antes.y_grid !== y_grid)) {
        const origen = { x_grid: antes.x_grid, y_grid: antes.y_grid };
        pushUndo(`mover ${antes.name ?? antes.nombre}`, async () => {
          await updateClassPosition(classId, origen);
          setClasses((prev) => prev.map((c) => (c.id === classId ? { ...c, ...origen } : c)));
        });
      }
    } catch {
      await loadClasses();
    }
  }

  // `undoable` es false cuando la tarjeta se reajusta sola al cambiar su
  // contenido (ver useAutoGrow): eso no es una acción del usuario.
  //
  // Redimensionar desde el borde superior o izquierdo también mueve la
  // posición (el borde opuesto queda fijo), así que x_grid/y_grid son
  // opcionales acá: solo vienen cuando el handle usado los cambió.
  async function handleResizeEnd(classId, { w_grid, h_grid, x_grid, y_grid }, { undoable = true } = {}) {
    const antes = classes.find((c) => c.id === classId);
    const patch = { w_grid, h_grid };
    if (x_grid !== undefined) patch.x_grid = x_grid;
    if (y_grid !== undefined) patch.y_grid = y_grid;
    try {
      await updateClassSize(classId, patch);
      setClasses((prev) => prev.map((c) => (c.id === classId ? { ...c, ...patch } : c)));

      const cambio = antes && (
        antes.w_grid !== w_grid || antes.h_grid !== h_grid ||
        (x_grid !== undefined && antes.x_grid !== x_grid) ||
        (y_grid !== undefined && antes.y_grid !== y_grid)
      );
      if (undoable && cambio) {
        const origen = {
          w_grid: antes.w_grid, h_grid: antes.h_grid,
          x_grid: antes.x_grid, y_grid: antes.y_grid,
        };
        pushUndo(`redimensionar ${antes.name ?? antes.nombre}`, async () => {
          await updateClassSize(classId, origen);
          setClasses((prev) => prev.map((c) => (c.id === classId ? { ...c, ...origen } : c)));
        });
      }
    } catch {
      await loadClasses();
    }
  }

  // ====== ELIMINAR CLASE ======
  async function handleDelete(classId) {
    if (!confirm("¿Eliminar esta clase?")) return;
    const clase = classes.find((c) => c.id === classId);
    const detalles = detailsByClass[classId];

    try {
      await apiDeleteClass(classId);
      setClasses((prev) => prev.filter((c) => c.id !== classId));
      setDetailsByClass((prev) => {
        const n = { ...prev };
        delete n[classId];
        return n;
      });
      if (selectedId === classId) setSelectedId(null);

      if (clase) {
        // Al deshacer se recrea la clase con sus atributos y métodos. Las
        // relaciones que la tocaban no se recuperan: el backend las borra en
        // cascada y la clase vuelve con otro id.
        pushUndo(`eliminar la clase ${clase.name ?? clase.nombre}`, async () => {
          const recreada = await apiCreateClass(diagram.id, {
            name: clase.name ?? clase.nombre,
            x_grid: clase.x_grid, y_grid: clase.y_grid,
            w_grid: clase.w_grid, h_grid: clase.h_grid,
            z_index: clase.z_index,
          });
          for (const a of detalles?.attrs || []) {
            await createAttribute(recreada.id, {
              name: a.name ?? a.nombre,
              type: a.type ?? a.tipo ?? "string",
              required: !!a.required,
            });
          }
          for (const m of detalles?.meths || []) {
            await createMethod(recreada.id, {
              name: m.name ?? m.nombre,
              return_type: m.return_type ?? "void",
            });
          }
          await loadClasses();
          await fetchDetails(recreada.id);
        });
      }
    } catch (e) {
      alert(e?.response?.data?.detail || "No se pudo eliminar");
    }
  }

  // ====== Clase de asociación (UML 2.5) ======
  // Cuando una relación muchos-a-muchos tiene atributos propios (o el
  // usuario simplemente quiere que la tabla intermedia sea explícita en el
  // diagrama, no solo un @JoinTable invisible generado por Hibernate), se
  // modela como una clase real conectada a ambos lados con multiplicidad 1.
  // Acá solo se crea la clase con sus dos FKs; las dos relaciones 1-a-* que
  // la conectan a las clases originales las arma quien llama a esto.
  async function createAssociationClass({ nameA, nameB, xGrid, yGrid }) {
    const usadosGlobal = classes.map((c) => (c.name ?? "").toLowerCase());
    const baseName = `${nameA}${nameB}`.replace(/\s+/g, "");
    const name = nextFreeName(baseName, usadosGlobal);

    const created = await apiCreateClass(diagram.id, {
      name,
      x_grid: xGrid, y_grid: yGrid, w_grid: 12, h_grid: 6, z_index: 1,
    });
    await loadClasses();
    replaceDetails(created.id, { attrs: [], meths: [] });

    const attrsUsados = [];
    const fkA = await createAttribute(created.id, {
      name: nextFreeName(`${nameA.toLowerCase()}_id`, attrsUsados),
      type: "integer",
      required: true,
    });
    attrsUsados.push(fkA.name);
    const fkB = await createAttribute(created.id, {
      name: nextFreeName(`${nameB.toLowerCase()}_id`, attrsUsados),
      type: "integer",
      required: true,
    });
    replaceDetails(created.id, { attrs: [fkA, fkB] });

    return created;
  }

  // ====== RETORNO ======
  return {
    classes, setClasses,
    selectedId, setSelectedId,
    selected,
    detailsByClass, replaceDetails,
    insertMode, setInsertMode,
    insertName, setInsertName,
    loadClasses, fetchDetails,
    handleCanvasClick,
    debouncedSave,
    handleRename,
    handleDragEnd,
    handleResizeEnd,
    handleDelete,
    createAssociationClass,

    // 🔹 atributos
    addAttr: async (classId) => {
      // El nombre por defecto tiene que ser único dentro de la clase: los
      // nombres repetidos están prohibidos a nivel de base de datos, así que
      // usar siempre "campo" hacía fallar el segundo que agregabas.
      const usados = (detailsByClass[classId]?.attrs || []).map((a) => a.name ?? a.nombre ?? "");
      const created = await createAttribute(classId, {
        name: nextFreeName("campo", usados),
        type: "string",
        required: false,
      });
      replaceDetails(classId, { attrs: [...(detailsByClass[classId]?.attrs || []), created] });

      pushUndo(`agregar el atributo ${created.name}`, async () => {
        await deleteAttribute(created.id);
        await fetchDetails(classId);
      });
      return created;
    },
    patchAttr: async (classId, attrId, patch) => {
      const updated = await updateAttribute(attrId, patch);
      const next = (detailsByClass[classId]?.attrs || []).map((a) => a.id === attrId ? updated : a);
      replaceDetails(classId, { attrs: next });
      return updated;
    },
    removeAttr: async (classId, attrId) => {
      const previo = (detailsByClass[classId]?.attrs || []).find((a) => a.id === attrId);
      await deleteAttribute(attrId);
      const next = (detailsByClass[classId]?.attrs || []).filter((a) => a.id !== attrId);
      replaceDetails(classId, { attrs: next });

      if (previo) {
        pushUndo(`eliminar el atributo ${previo.name ?? previo.nombre}`, async () => {
          await createAttribute(classId, {
            name: previo.name ?? previo.nombre,
            type: previo.type ?? previo.tipo ?? "string",
            required: !!previo.required,
          });
          await fetchDetails(classId);
        });
      }
    },

    // 🔹 métodos
    addMeth: async (classId) => {
      const usados = (detailsByClass[classId]?.meths || []).map((m) => m.name ?? m.nombre ?? "");
      const created = await createMethod(classId, {
        name: nextFreeName("operacion", usados),
        return_type: "void",
      });
      replaceDetails(classId, { meths: [...(detailsByClass[classId]?.meths || []), created] });

      pushUndo(`agregar el método ${created.name}`, async () => {
        await deleteMethod(created.id);
        await fetchDetails(classId);
      });
      return created;
    },
    patchMeth: async (classId, methId, patch) => {
      const updated = await updateMethod(methId, patch);
      const next = (detailsByClass[classId]?.meths || []).map((m) => m.id === methId ? updated : m);
      replaceDetails(classId, { meths: next });
      return updated;
    },
    removeMeth: async (classId, methId) => {
      const previo = (detailsByClass[classId]?.meths || []).find((m) => m.id === methId);
      await deleteMethod(methId);
      const next = (detailsByClass[classId]?.meths || []).filter((m) => m.id !== methId);
      replaceDetails(classId, { meths: next });

      if (previo) {
        pushUndo(`eliminar el método ${previo.name ?? previo.nombre}`, async () => {
          await createMethod(classId, {
            name: previo.name ?? previo.nombre,
            return_type: previo.return_type ?? "void",
          });
          await fetchDetails(classId);
        });
      }
    },
  };
}
