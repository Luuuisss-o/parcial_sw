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
