// src/components/panels/AiAssistantPanel.jsx
//
// Asistente que edita el diagrama por lenguaje natural (texto o voz).
//
// El comando NO se resuelve en la respuesta HTTP: el backend lo encola y
// responde al instante, y tanto el progreso como el resultado llegan por el
// WebSocket del diagrama (eventos ai.started / ai.done / ai.error). Se hizo
// así porque la latencia del modelo es muy variable y dejar la petición
// abierta congelaba la interfaz. Como efecto secundario, las clases y
// atributos van apareciendo en el lienzo a medida que se ejecutan.

import { useEffect, useRef, useState } from "react";
import { sendAiCommand } from "../../api/ai";
import { transcribeAudio } from "../../api/voice";
import { onEvent } from "../../api/realtime";
import Icon from "../common/Icon";

const EJEMPLOS = [
  "Creá una clase Cliente",
  "Agregale a Cliente los atributos nombre, email y teléfono",
  "Creá una relación de uno a muchos entre Cliente y Pedido",
  "Ponele a Pedido un atributo total de tipo Double",
];

export default function AiAssistantPanel({ diagramId }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [log, setLog] = useState([]); // {role: 'user'|'assistant'|'error', text}
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const logEndRef = useRef(null);

  // ---- Resultados del asistente (llegan por WebSocket) ----
  useEffect(() => {
    if (!diagramId) return;
    const offs = [
      onEvent("ai.done", ({ reply }) => {
        setLog((prev) => [...prev, { role: "assistant", text: reply }]);
        setBusy(false);
      }),
      onEvent("ai.error", ({ detail }) => {
        setLog((prev) => [...prev, { role: "error", text: detail }]);
        setBusy(false);
      }),
    ];
    return () => offs.forEach((off) => off());
  }, [diagramId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log, busy]);

  const send = async (commandText) => {
    const value = (commandText ?? text).trim();
    if (!value || busy) return;

    setLog((prev) => [...prev, { role: "user", text: value }]);
    setText("");
    setBusy(true);

    try {
      await sendAiCommand(diagramId, value);
      // El resultado llega por WebSocket; acá solo confirmamos que se encoló.
    } catch (err) {
      const detail =
        err?.response?.data?.detail || "No se pudo enviar el comando al servidor.";
      setLog((prev) => [...prev, { role: "error", text: detail }]);
      setBusy(false);
    }
  };

  // Graba audio con MediaRecorder y lo manda al backend para que Gemini lo
  // transcriba (ver api/voice.js). No usa la Web Speech API del navegador:
  // esa transcribe del lado del cliente contra los servidores de Google y
  // en la práctica es inestable (solo Chromium, falla sin aviso claro).
  // Acá el audio grabado se sube como archivo y el texto que vuelve entra
  // al mismo flujo que un comando escrito a mano.
  const toggleVoice = async () => {
    console.log("[voice] toggleVoice, listening=", listening);
    if (listening) {
      mediaRecorderRef.current?.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      console.log("[voice] getUserMedia no existe en este navegador");
      setLog((prev) => [
        ...prev,
        { role: "error", text: "Este navegador no permite grabar audio." },
      ]);
      return;
    }
    if (!window.isSecureContext) {
      console.log("[voice] contexto no seguro (ni https ni localhost)");
      setLog((prev) => [
        ...prev,
        { role: "error", text: "El micrófono solo funciona por HTTPS o en localhost." },
      ]);
      return;
    }

    let stream;
    try {
      console.log("[voice] pidiendo getUserMedia...");
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      console.log("[voice] permiso concedido, stream:", stream, "tracks:", stream.getAudioTracks());
    } catch (err) {
      console.error("[voice] getUserMedia rechazado:", err?.name, err?.message, err);
      setLog((prev) => [
        ...prev,
        {
          role: "error",
          text: `No se pudo acceder al micrófono (${err?.name || "error"}). Revisá los permisos del navegador para este sitio.`,
        },
      ]);
      return;
    }

    let recorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch (err) {
      console.error("[voice] MediaRecorder no se pudo crear:", err);
      setLog((prev) => [
        ...prev,
        { role: "error", text: "Este navegador no puede grabar audio en el formato soportado." },
      ]);
      return;
    }
    audioChunksRef.current = [];
    recorder.ondataavailable = (e) => {
      console.log("[voice] ondataavailable, size:", e.data.size);
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    recorder.onerror = (e) => {
      console.error("[voice] MediaRecorder error:", e.error);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setListening(false);

      const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
      console.log("[voice] blob grabado:", blob.size, "bytes, mimeType:", recorder.mimeType);
      if (blob.size === 0) {
        setLog((prev) => [
          ...prev,
          {
            role: "error",
            text: "No se grabó audio. Probá mantener apretado el micrófono más tiempo, o revisá que esté eligiendo el dispositivo correcto en los permisos del navegador.",
          },
        ]);
        return;
      }

      setTranscribing(true);
      try {
        const transcript = await transcribeAudio(blob);
        if (transcript) send(transcript);
      } catch (err) {
        const detail =
          err?.response?.data?.detail || "No se pudo transcribir el audio.";
        setLog((prev) => [...prev, { role: "error", text: detail }]);
      } finally {
        setTranscribing(false);
      }
    };

    mediaRecorderRef.current = recorder;
    recorder.start();
    setListening(true);
  };

  // ---------------- Botón flotante (cerrado) ----------------
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="btn btn-primary"
        style={{
          position: "absolute",
          right: "var(--sp-4)",
          bottom: "var(--sp-4)",
          height: 44,
          padding: "0 var(--sp-4)",
          borderRadius: 999,
          boxShadow: "var(--shadow)",
          zIndex: "var(--z-float)",
        }}
      >
        <Icon name="sparkles" size={18} />
        Asistente
      </button>
    );
  }

  // ---------------- Panel abierto ----------------
  return (
    <div
      className="panel"
      style={{
        position: "absolute",
        right: "var(--sp-4)",
        bottom: "var(--sp-4)",
        width: 380,
        height: 460,
        display: "flex",
        flexDirection: "column",
        boxShadow: "var(--shadow-lg)",
        zIndex: "var(--z-float)",
        overflow: "hidden",
      }}
    >
      {/* Encabezado */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
          padding: "var(--sp-3) var(--sp-4)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Icon name="sparkles" size={16} style={{ color: "var(--accent)" }} />
        <strong style={{ fontSize: 13, flex: 1 }}>Asistente del diagrama</strong>
        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setOpen(false)} title="Cerrar">
          <Icon name="close" size={15} />
        </button>
      </div>

      {/* Conversación */}
      <div
        className="scroll"
        style={{ flex: 1, padding: "var(--sp-4)", display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}
      >
        {log.length === 0 && (
          <div style={{ display: "grid", gap: "var(--sp-3)" }}>
            <p className="text-muted" style={{ margin: 0, fontSize: 13 }}>
              Escribí lo que querés hacer y yo lo aplico en el diagrama. Probá con uno
              de estos ejemplos:
            </p>
            <div style={{ display: "grid", gap: "var(--sp-2)" }}>
              {EJEMPLOS.map((ej) => (
                <button
                  key={ej}
                  onClick={() => send(ej)}
                  style={{
                    textAlign: "left",
                    padding: "var(--sp-2) var(--sp-3)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    background: "var(--surface-2)",
                    color: "var(--text)",
                    font: "inherit",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {ej}
                </button>
              ))}
            </div>
          </div>
        )}

        {log.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "88%",
              padding: "var(--sp-2) var(--sp-3)",
              borderRadius: "var(--radius)",
              fontSize: 13,
              lineHeight: 1.45,
              ...(m.role === "user"
                ? { background: "var(--accent)", color: "var(--accent-text)" }
                : m.role === "error"
                ? { background: "var(--danger-soft)", color: "var(--danger)", border: "1px solid var(--danger)" }
                : { background: "var(--surface-2)", color: "var(--text)" }),
            }}
          >
            {m.role === "error" && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2, fontWeight: 600 }}>
                <Icon name="warning" size={13} />
                No se pudo completar
              </div>
            )}
            {m.text}
          </div>
        ))}

        {busy && (
          <div
            className="text-muted"
            style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", fontSize: 12 }}
          >
            <Icon name="loader" size={14} className="spinning" />
            Aplicando los cambios en el diagrama…
          </div>
        )}
        <div ref={logEndRef} />
      </div>

      {/* Entrada */}
      <div
        style={{
          display: "flex",
          gap: "var(--sp-2)",
          padding: "var(--sp-3)",
          borderTop: "1px solid var(--border)",
        }}
      >
        <input
          className="input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={
            listening
              ? "Grabando… tocá el micrófono de nuevo para terminar"
              : transcribing
              ? "Transcribiendo…"
              : "Ej: creá una clase Factura"
          }
          disabled={busy || transcribing}
        />
        <button
          className={`btn btn-icon ${listening ? "btn-active" : ""}`}
          onClick={toggleVoice}
          disabled={busy || transcribing}
          title={listening ? "Detener grabación" : "Dictar por voz"}
        >
          <Icon name={transcribing ? "loader" : "mic"} className={transcribing ? "spinning" : ""} />
        </button>
        <button
          className="btn btn-primary btn-icon"
          onClick={() => send()}
          disabled={busy || !text.trim()}
          title="Enviar comando"
        >
          <Icon name="send" />
        </button>
      </div>
    </div>
  );
}
