
// // src/hooks/useRelations.js
import { useEffect, useState } from "react";
import {
  listRelations,
  getRelation,                // 👈 importa esta
  createRelation as apiCreateRelation,
  updateRelation as apiUpdateRelation,
  deleteRelation as apiDeleteRelation,
} from "../api/relations";
import { onEvent } from "../api/realtime";
import useUndo from "../store/undo";

export default function useRelations(diagram) {
  const [relations, setRelations] = useState([]);
  const [selectedRelId, setSelectedRelId] = useState(null);
  const [selectedRelation, setSelectedRelation] = useState(null); // 👈 ya no usamos solo find()
  const pushUndo = useUndo((s) => s.push);

  // ====== CARGA INICIAL ======
  async function loadRelations() {
    if (!diagram?.id) return;
    try {
      const items = await listRelations(diagram.id);
      setRelations(items || []);
      if (selectedRelId && !items?.some((x) => x.id === selectedRelId)) {
        setSelectedRelId(null);
        setSelectedRelation(null);
      }
    } catch {
      setRelations([]);
    }
  }

  useEffect(() => {
    if (diagram) loadRelations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagram]);

  // ====== FETCH RELACIÓN SELECCIONADA ======
  useEffect(() => {
    if (!selectedRelId) {
      setSelectedRelation(null);
      return;
    }
    (async () => {
      try {
        const rel = await getRelation(selectedRelId); // 👈 ahora traes la data fresca
        setSelectedRelation(rel);
      } catch {
        setSelectedRelation(null);
      }
    })();
  }, [selectedRelId]);

  // ====== CRUD ======
  async function createRelation(body) {
    const creada = await apiCreateRelation(diagram.id, body);
    pushUndo(`crear la relación ${creada.origen_nombre} → ${creada.destino_nombre}`, async () => {
      await apiDeleteRelation(creada.id);
      setRelations((prev) => prev.filter((r) => r.id !== creada.id));
    });
    return creada;
  }

  async function updateRelation(relationId, patch) {
    return await apiUpdateRelation(relationId, patch);
  }

  async function deleteRelation(relationId) {
    if (!confirm("¿Eliminar esta relación?")) return;
    const previa = relations.find((r) => r.id === relationId);
    const res = await apiDeleteRelation(relationId);

    if (previa) {
      pushUndo(`eliminar la relación ${previa.origen_nombre} → ${previa.destino_nombre}`, async () => {
        await apiCreateRelation(diagram.id, {
          // La lista viene con los alias en español (origen_id, tipo,
          // mult_origen_min...) y los eventos en vivo con los nombres en
          // inglés: se aceptan los dos.
          from_class: previa.from_class ?? previa.origen_id,
          to_class: previa.to_class ?? previa.destino_id,
          type: previa.type ?? previa.tipo,
          label: previa.label ?? previa.etiqueta,
          src_anchor: previa.src_anchor,
          dst_anchor: previa.dst_anchor,
          src_offset: previa.src_offset,
          dst_offset: previa.dst_offset,
          src_lane: previa.src_lane,
          dst_lane: previa.dst_lane,
          src_mult_min: previa.src_mult_min ?? previa.mult_origen_min,
          src_mult_max: previa.src_mult_max ?? previa.mult_origen_max,
          dst_mult_min: previa.dst_mult_min ?? previa.mult_destino_min,
          dst_mult_max: previa.dst_mult_max ?? previa.mult_destino_max,
          es_clase_asociacion: previa.es_clase_asociacion,
          src_role: previa.src_role ?? previa.rol_origen,
          dst_role: previa.dst_role ?? previa.rol_destino,
          src_navigable: previa.src_navigable ?? previa.navegable_origen,
          dst_navigable: previa.dst_navigable ?? previa.navegable_destino,
        });
        await loadRelations();
      });
    }
    return res;
  }

  // ====== EVENTOS EN TIEMPO REAL ======
  useEffect(() => {
    if (!diagram?.id) return;

    // onEvent devuelve la función para desuscribirse: hay que llamarlas en el
    // cleanup, si no cada re-ejecución del efecto acumula listeners duplicados
    // y cada relación entrante se aplicaría varias veces.
    const offs = [
      // Tras reconectar: recargar lo que cambió mientras no había conexión.
      onEvent("reconnected", () => loadRelations()),
      onEvent("relation.created", (rel) => {
        if (rel.diagram_id === diagram.id) {
          setRelations((prev) =>
            prev.some((r) => r.id === rel.id) ? prev : [...prev, rel]
          );
        }
      }),

      onEvent("relation.updated", (rel) => {
        if (rel.diagram_id === diagram.id) {
          setRelations((prev) =>
            prev.map((r) => (r.id === rel.id ? { ...r, ...rel } : r))
          );
          if (selectedRelId === rel.id) {
            setSelectedRelation(rel); // actualiza también el detalle abierto
          }
        }
      }),

      onEvent("relation.deleted", ({ id, diagram_id }) => {
        if (diagram_id === diagram.id) {
          setRelations((prev) => prev.filter((r) => r.id !== id));
          if (selectedRelId === id) {
            setSelectedRelId(null);
            setSelectedRelation(null);
          }
        }
      }),
    ];

    return () => offs.forEach((off) => off());
  }, [diagram, selectedRelId]);

  return {
    relations,
    selectedRelId,
    setSelectedRelId,
    selectedRelation,   // 👈 ahora viene desde getRelation
    loadRelations,
    createRelation,
    updateRelation,
    deleteRelation,
  };
}
