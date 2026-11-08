import api from "./client";

/**
 * Sube un audio grabado en el navegador (dictado por voz) y devuelve el
 * texto transcripto por Gemini. No aplica ningún cambio al diagrama: el
 * texto resultante se manda aparte a sendAiCommand, igual que si el
 * usuario lo hubiera escrito a mano.
 *
 * Timeout propio, más largo que el default del cliente: el backend
 * reintenta contra Gemini con backoff si está saturado.
 */
export const transcribeAudio = async (blob) => {
  const form = new FormData();
  form.append("file", blob, "audio.webm");
  const res = await api.post("/voice/transcribe", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 45000,
  });
  return res.data.text;
};
