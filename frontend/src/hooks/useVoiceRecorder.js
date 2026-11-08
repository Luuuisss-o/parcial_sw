// src/hooks/useVoiceRecorder.js
//
// Graba audio con MediaRecorder y lo manda al backend para que Gemini lo
// transcriba (ver api/voice.js). No usa la Web Speech API del navegador:
// esa transcribe del lado del cliente contra los servidores de Google y en
// la práctica es inestable (solo Chromium, falla sin aviso claro).
//
// Extraído del antiguo panel del asistente para reutilizarlo en el chat del
// equipo: el texto transcripto se le entrega a `onTranscript` y el error
// (si lo hay) a `onError`, siempre como texto listo para mostrar.

import { useRef, useState } from "react";
import { transcribeAudio } from "../api/voice";

export default function useVoiceRecorder({ onTranscript, onError }) {
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);

  const toggle = async () => {
    if (listening) {
      recorderRef.current?.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      onError("Este navegador no permite grabar audio.");
      return;
    }
    if (!window.isSecureContext) {
      onError("El micrófono solo funciona por HTTPS o en localhost.");
      return;
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      onError(
        `No se pudo acceder al micrófono (${err?.name || "error"}). Revisá los permisos del navegador para este sitio.`
      );
      return;
    }

    let recorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      onError("Este navegador no puede grabar audio en el formato soportado.");
      return;
    }

    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setListening(false);

      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      if (blob.size === 0) {
        onError(
          "No se grabó audio. Probá hablar un poco más, o revisá que el navegador esté usando el micrófono correcto."
        );
        return;
      }

      setTranscribing(true);
      try {
        const transcript = await transcribeAudio(blob);
        if (transcript) onTranscript(transcript);
      } catch (err) {
        onError(err?.response?.data?.detail || "No se pudo transcribir el audio.");
      } finally {
        setTranscribing(false);
      }
    };

    recorderRef.current = recorder;
    recorder.start();
    setListening(true);
  };

  return { listening, transcribing, toggle };
}
