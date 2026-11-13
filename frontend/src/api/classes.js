import api from "./client";

// ===== Helper para mapear nombre → name =====
const mapClass = (c) => ({
  id: c.id,
  name: c.nombre ?? c.name,
  kind: c.tipo_clase ?? c.kind ?? "class",
  x_grid: c.x_grid,
  y_grid: c.y_grid,
  w_grid: c.w_grid,
  h_grid: c.h_grid,
  z_index: c.z_index,
});

// ====== CLASES ======

export const listClasses = async (diagramId) => {
  console.log("📥 [listClasses] GET", diagramId);
  try {
    const r = await api.get(`/diagrams/${diagramId}/classes`);
    console.log("✅ [listClasses] response:", r.data);
    return (r.data || []).map(mapClass);
  } catch (err) {
    console.error("❌ [listClasses] error:", err?.response?.data || err);
    throw err;
  }
};

export const createClass = async (
  diagramId,
  { name, kind, x_grid, y_grid, w_grid, h_grid, z_index } = {}
) => {
  const body = { name, kind, x_grid, y_grid, w_grid, h_grid, z_index };
  console.log("📤 [createClass] POST body:", body);
  try {
    const r = await api.post(`/diagrams/${diagramId}/classes`, body);
    console.log("✅ [createClass] response:", r.data);
    return mapClass(r.data);
  } catch (err) {
    console.error("❌ [createClass] error:", err?.response?.data || err);
    throw err;
  }
};

export const updateClass = async (classId, patch) => {
  console.log("📤 [updateClass] PATCH body:", patch);
  try {
    const r = await api.patch(`/diagrams/classes/${classId}`, patch);
    console.log("✅ [updateClass] response:", r.data);
    return mapClass(r.data);
  } catch (err) {
    console.error("❌ [updateClass] error:", err?.response?.data || err);
    throw err;
  }
};

export const deleteClass = async (classId) => {
  console.log("🗑️ [deleteClass] DELETE", classId);
  try {
    const r = await api.delete(`/diagrams/classes/${classId}`);
    console.log("✅ [deleteClass] OK");
    return r.data;
  } catch (err) {
    console.error("❌ [deleteClass] error:", err?.response?.data || err);
    throw err;
  }
};

// ====== HELPERS DE CLASE ======

export const updateClassPosition = (classId, { x_grid, y_grid }) =>
  updateClass(classId, { x_grid, y_grid });

export const updateClassSize = (classId, { w_grid, h_grid, x_grid, y_grid }) =>
  updateClass(classId, { w_grid, h_grid, ...(x_grid !== undefined ? { x_grid } : {}), ...(y_grid !== undefined ? { y_grid } : {}) });

export const updateClassZ = (classId, z_index) =>
  updateClass(classId, { z_index });

// ====== ATRIBUTOS ======

export const listAttributes = async (classId) => {
  console.log("📥 [listAttributes] GET", classId);
  try {
    const r = await api.get(`/diagrams/classes/${classId}/attributes`);
    console.log("✅ [listAttributes] response:", r.data);
    return r.data;
  } catch (err) {
    console.error("❌ [listAttributes] error:", err?.response?.data || err);
    throw err;
  }
};

// Notación UML 2.5 opcional: visibility, is_static, is_derived,
// multiplicity, default_value (si no vienen, el backend usa sus defaults).
export const createAttribute = async (classId, { name, type, required = false, ...notation }) => {
  const body = { name, type, required, ...notation };
  console.log("📤 [createAttribute] POST body:", body);
  try {
    const r = await api.post(`/diagrams/classes/${classId}/attributes`, body);
    console.log("✅ [createAttribute] response:", r.data);
    return r.data;
  } catch (err) {
    console.error("❌ [createAttribute] error:", err?.response?.data || err);
    throw err;
  }
};

export const updateAttribute = async (attrId, patch) => {
  console.log("📤 [updateAttribute] PATCH body:", patch);
  try {
    const r = await api.patch(`/diagrams/attributes/${attrId}`, patch);
    console.log("✅ [updateAttribute] response:", r.data);
    return r.data;
  } catch (err) {
    console.error("❌ [updateAttribute] error:", err?.response?.data || err);
    throw err;
  }
};

export const deleteAttribute = async (attrId) => {
  console.log("🗑️ [deleteAttribute] DELETE", attrId);
  try {
    const r = await api.delete(`/diagrams/attributes/${attrId}`);
    console.log("✅ [deleteAttribute] OK");
    return r.data;
  } catch (err) {
    console.error("❌ [deleteAttribute] error:", err?.response?.data || err);
    throw err;
  }
};

// ====== MÉTODOS ======

export const listMethods = async (classId) => {
  console.log("📥 [listMethods] GET", classId);
  try {
    const r = await api.get(`/diagrams/classes/${classId}/methods`);
    console.log("✅ [listMethods] response:", r.data);
    return r.data;
  } catch (err) {
    console.error("❌ [listMethods] error:", err?.response?.data || err);
    throw err;
  }
};

// Notación UML 2.5 opcional: visibility, is_static, is_abstract, params.
export const createMethod = async (classId, { name, return_type = "void", ...notation }) => {
  const body = { name, return_type, ...notation };
  console.log("📤 [createMethod] POST body:", body);
  try {
    const r = await api.post(`/diagrams/classes/${classId}/methods`, body);
    console.log("✅ [createMethod] response:", r.data);
    return r.data;
  } catch (err) {
    console.error("❌ [createMethod] error:", err?.response?.data || err);
    throw err;
  }
};

export const updateMethod = async (methodId, patch) => {
  console.log("📤 [updateMethod] PATCH body:", patch);
  try {
    const r = await api.patch(`/diagrams/methods/${methodId}`, patch);
    console.log("✅ [updateMethod] response:", r.data);
    return r.data;
  } catch (err) {
    console.error("❌ [updateMethod] error:", err?.response?.data || err);
    throw err;
  }
};

export const deleteMethod = async (methodId) => {
  console.log("🗑️ [deleteMethod] DELETE", methodId);
  try {
    const r = await api.delete(`/diagrams/methods/${methodId}`);
    console.log("✅ [deleteMethod] OK");
    return r.data;
  } catch (err) {
    console.error("❌ [deleteMethod] error:", err?.response?.data || err);
    throw err;
  }
};
