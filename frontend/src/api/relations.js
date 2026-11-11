import api from "./client";

// 🔹 Helper: elimina las claves cuyo valor es `undefined`
const omitUndefined = (obj) =>
  Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined));

// 🔹 Helper: normaliza valores de multiplicidad (*, vacíos, null → null; números válidos → Number)
const normalizeMult = (val) => {
  if (val === "*" || val === "" || val == null) return null;
  const n = Number(val);
  return isNaN(n) ? null : n;
};

// ====== RELATIONS API ======

/**
 * Lista todas las relaciones de un diagrama
 */
export const listRelations = (diagramId) => {
  console.log("📤 [listRelations] GET:", diagramId);
  return api.get(`/diagrams/${diagramId}/relations`)
    .then((r) => {
      console.log("✅ [listRelations] response:", r.data);
      return r.data;
    })
    .catch((err) => {
      console.error("❌ [listRelations] error:", err?.response?.data || err);
      throw err;
    });
};

/**
 * Crear una relación entre dos clases
 */
export const createRelation = (diagramId, params) => {
  const body = omitUndefined({
    from_class: params.from_class,
    to_class: params.to_class,
    type: params.type,
    label: params.label,
    src_anchor: params.src_anchor,
    dst_anchor: params.dst_anchor,
    src_offset: params.src_offset,
    dst_offset: params.dst_offset,
    src_lane: params.src_lane,
    dst_lane: params.dst_lane,
    src_mult_min: normalizeMult(params.src_mult_min),
    src_mult_max: normalizeMult(params.src_mult_max),
    dst_mult_min: normalizeMult(params.dst_mult_min),
    dst_mult_max: normalizeMult(params.dst_mult_max),
    es_clase_asociacion: params.es_clase_asociacion,
    src_role: params.src_role,
    dst_role: params.dst_role,
    src_navigable: params.src_navigable,
    dst_navigable: params.dst_navigable,
  });

  console.log("📤 [createRelation] POST body:", body);

  return api.post(`/diagrams/${diagramId}/relations`, body)
    .then((r) => {
      console.log("✅ [createRelation] response:", r.data);
      return r.data;
    })
    .catch((err) => {
      console.error("❌ [createRelation] error:", err?.response?.data || err);
      throw err;
    });
};

/**
 * Actualizar una relación existente. Es un PATCH parcial de verdad: un campo
 * de multiplicidad ausente en `patch` (RelationInspector siempre los manda
 * los 4 con valores reales, pero por ejemplo ConnectionLayer -- al arrastrar
 * un extremo de la línea -- solo manda src_anchor/dst_anchor) tiene que
 * quedar afuera del body, no viajar como `null`. normalizeMult(undefined)
 * devuelve `null` (trata "sin valor" como "sin límite"), así que omitUndefined
 * -- que solo filtra `undefined` estricto -- lo dejaba pasar igual: el
 * backend lo interpretaba como "poné la multiplicidad en null", y esa
 * columna es NOT NULL, así que el update fallaba con un 500 apenas se movía
 * un extremo de una relación sin tocar también su multiplicidad.
 */
export const updateRelation = (relationId, patch = {}) => {
  const body = omitUndefined({
    type: patch.type,
    label: patch.label,
    src_anchor: patch.src_anchor,
    dst_anchor: patch.dst_anchor,
    src_offset: patch.src_offset,
    dst_offset: patch.dst_offset,
    src_lane: patch.src_lane,
    dst_lane: patch.dst_lane,
    src_mult_min: "src_mult_min" in patch ? normalizeMult(patch.src_mult_min) : undefined,
    src_mult_max: "src_mult_max" in patch ? normalizeMult(patch.src_mult_max) : undefined,
    dst_mult_min: "dst_mult_min" in patch ? normalizeMult(patch.dst_mult_min) : undefined,
    dst_mult_max: "dst_mult_max" in patch ? normalizeMult(patch.dst_mult_max) : undefined,
    src_role: patch.src_role,
    dst_role: patch.dst_role,
    src_navigable: patch.src_navigable,
    dst_navigable: patch.dst_navigable,
  });

  console.log("📤 [updateRelation] PATCH body:", { relationId, ...body });

  return api.patch(`/diagrams/relations/${relationId}`, body)
    .then((r) => {
      console.log("✅ [updateRelation] response:", r.data);
      return r.data;
    })
    .catch((err) => {
      console.error("❌ [updateRelation] error:", err?.response?.data || err);
      throw err;
    });
};

/**
 * Eliminar una relación
 */
export const deleteRelation = (relationId) => {
  console.log("📤 [deleteRelation] DELETE:", relationId);
  return api.delete(`/diagrams/relations/${relationId}`)
    .then(() => {
      console.log("✅ [deleteRelation] eliminado:", relationId);
      return true;
    })
    .catch((err) => {
      console.error("❌ [deleteRelation] error:", err?.response?.data || err);
      throw err;
    });
};

/**
 * Obtener una relación por ID
 */
export const getRelation = (relationId) => {
  console.log("📤 [getRelation] GET:", relationId);
  return api.get(`/diagrams/relations/${relationId}`)
    .then((r) => {
      console.log("✅ [getRelation] response:", r.data);
      return r.data;
    })
    .catch((err) => {
      console.error("❌ [getRelation] error:", err?.response?.data || err);
      throw err;
    });
};
