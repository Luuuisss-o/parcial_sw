import api from "./client";

/**
 * Descarga el diagrama como archivo .xmi (interoperabilidad con Enterprise
 * Architect). Usa axios en vez de fetch para que viaje el header de auth
 * del interceptor, igual que el resto de la app.
 */
export const exportXmi = async (diagramId, title) => {
  const res = await api.get(`/diagrams/${diagramId}/export-xmi`, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(res.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${(title || "diagrama").replace(/\s+/g, "_")}.xmi`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

/**
 * Sube un archivo .xmi y lo mezcla en el diagrama. Devuelve un resumen
 * {classes_created, classes_skipped, attributes_created, ..., warnings}.
 * Los cambios aplicados llegan solos por el WebSocket, igual que cualquier
 * otra edición: no hace falta recargar nada acá.
 */
export const importXmi = async (diagramId, file) => {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post(`/diagrams/${diagramId}/import-xmi`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
};
