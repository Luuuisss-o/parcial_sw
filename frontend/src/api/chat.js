import api from "./client";

// Chat grupal del diagrama (Fase 2).
//
// Los mensajes nuevos NO se leen de la respuesta del POST: llegan a todos
// (incluido quien lo mandó) por el WebSocket del diagrama como evento
// `chat.message`, así el orden es el mismo para todo el equipo. El POST solo
// devuelve el mensaje creado para poder confirmarlo de inmediato.
//
// Una consulta a la IA es un mensaje más: escribir "@IA ..." en el texto o
// mandar `askAi: true`. La respuesta llega después como otro `chat.message`
// con role "ASSISTANT" dirigido a quien preguntó, visible para todos.

/** Historial (más viejos primero). `beforeSeq` pagina hacia atrás. */
export const listChat = (diagramId, { limit = 50, beforeSeq } = {}) =>
  api
    .get(`/diagrams/${diagramId}/chat`, {
      params: { limit, ...(beforeSeq != null ? { before_seq: beforeSeq } : {}) },
    })
    .then((r) => r.data);

/** Envía un mensaje al chat del diagrama. */
export const sendChat = (diagramId, text, { askAi = false } = {}) =>
  api.post(`/diagrams/${diagramId}/chat`, { text, ask_ai: askAi }).then((r) => r.data);

/** Configuración de la IA del diagrama: { solutions_enabled }. */
export const getAiSettings = (diagramId) =>
  api.get(`/diagrams/${diagramId}/ai/settings`).then((r) => r.data);

/** Solo el dueño: habilita/deshabilita que la IA entregue soluciones de diseño. */
export const updateAiSettings = (diagramId, settings) =>
  api.patch(`/diagrams/${diagramId}/ai/settings`, settings).then((r) => r.data);

/** Solo el dueño: prueba el proveedor de IA configurado. → { ok, provider_label, detail } */
export const testAiSettings = (diagramId) =>
  api.post(`/diagrams/${diagramId}/ai/settings/test`, null, { timeout: 200000 }).then((r) => r.data);

/**
 * Propuesta del asesor (segundo parcial): aceptarla la aplica al diagrama
 * (si las clases involucradas no cambiaron; si cambiaron queda "stale").
 * Solo quien hizo la consulta o el dueño del diagrama. → la propuesta actualizada.
 */
export const decideProposal = (diagramId, proposalId, accept) =>
  api
    .post(`/diagrams/${diagramId}/ai/proposals/${proposalId}/${accept ? "accept" : "reject"}`)
    .then((r) => r.data);
