import api from "./client";

/**
 * Encola un comando en lenguaje natural (texto, o voz ya transcripta) para
 * que el asistente edite el diagrama.
 *
 * Responde apenas se encola (202). El resultado NO viene acá: llega por el
 * WebSocket del diagrama como evento `ai.done` o `ai.error`, y los cambios
 * en sí llegan como los eventos normales (class.created, attribute.created…),
 * igual que si otro usuario los hubiera hecho a mano.
 */
export const sendAiCommand = (diagramId, text) => {
  return api
    .post(`/diagrams/${diagramId}/ai/command`, { text })
    .then((r) => r.data)
    .catch((err) => {
      console.error("[sendAiCommand] error:", err?.response?.data || err);
      throw err;
    });
};
