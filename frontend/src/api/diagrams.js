import api from "./client";

// ====== Crear un diagrama ======
/**
 * Crea un nuevo diagrama en el backend.
 * @param {string} title - título del diagrama
 * @returns {object} DiagramOut - el diagrama creado
 */
export async function createDiagram(title) {
  const { data } = await api.post("/diagrams", { title });
  return data; // DiagramOut (objeto con id, title, etc.)
}

// ====== Listar diagramas ======
/**
 * Lista diagramas con paginación.
 * @param {object} params - { page, limit }
 * @returns {object} { items, page, limit, total }
 */
export async function listDiagrams({ page = 1, limit = 20 } = {}) {
  const { data } = await api.get("/diagrams", { params: { page, limit } });
  return data; // lista paginada de diagramas
}

// ====== Obtener un diagrama ======
/**
 * Obtiene un diagrama por su ID.
 * @param {string} id - id del diagrama
 * @returns {object} DiagramOut
 */
export async function getDiagram(id) {
  const { data } = await api.get(`/diagrams/${id}`);
  return data; // objeto con detalles del diagrama
}

// ====== Eliminar un diagrama ======
/**
 * Elimina un diagrama por ID.
 * @param {string} id - id del diagrama
 */
export async function deleteDiagram(id) {
  await api.delete(`/diagrams/${id}`);
}

// ====== Colaboradores ======
export async function listCollaborators(diagramId) {
  const { data } = await api.get(`/diagrams/${diagramId}/collaborators`);
  return data;
}

export async function addCollaborator(diagramId, email, role = "EDITOR") {
  const { data } = await api.post(`/diagrams/${diagramId}/collaborators`, { email, role });
  return data;
}

export async function removeCollaborator(diagramId, userId) {
  await api.delete(`/diagrams/${diagramId}/collaborators/${userId}`);
}
