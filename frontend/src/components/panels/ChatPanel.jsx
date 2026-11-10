// src/components/panels/ChatPanel.jsx
//
// Chat del equipo (Fase 2 · CU-14, CU-15, CU-16).
//
// Un solo canal para todo el diagrama: los colaboradores conversan entre sí
// y, cuando alguien escribe "@IA …" (o activa el botón de la IA), la
// pregunta se le hace al asistente. Tanto la pregunta como la respuesta son
// públicas: todos las ven, y la respuesta va dirigida por nombre a quien
// preguntó. Reemplaza al antiguo panel privado del asistente.

import { useEffect, useMemo, useRef, useState } from "react";
import useTeamChat from "../../hooks/useTeamChat";
import useVoiceRecorder from "../../hooks/useVoiceRecorder";
import Icon from "../common/Icon";
import ChatMarkdown from "../common/ChatMarkdown";
import AiSettingsBar from "./AiSettingsBar";
import ProposalCard from "./ProposalCard";

// Misma paleta y mismo cálculo que el backend (realtime._cursor_color):
// suma de bytes UTF-8 del email, así el color del autor en el chat coincide
// con el de su cursor en el lienzo.
const PALETTE = ["#f97316", "#22c55e", "#3b82f6", "#ec4899", "#a855f7", "#14b8a6", "#eab308", "#ef4444"];
const encoder = new TextEncoder();
const colorFor = (email) =>
  email ? PALETTE[encoder.encode(email).reduce((a, b) => a + b, 0) % PALETTE.length] : "var(--text-muted)";

const AI_MENTION_RE = /(?<![\w@.])@(?:ia|ai|asistente)\b/gi;
const hasAiMention = (t) => new RegExp(AI_MENTION_RE.source, "i").test(t);

// La IA cumple dos roles: edita el diagrama cuando se le pide un cambio y
// actúa como mentora de diseño cuando la consulta es teórica.
const SUGERENCIAS = [
  "@IA creá una clase Cliente con nombre, email y teléfono",
  "@IA relacioná Cliente y Pedido de uno a muchos",
  "@IA ¿qué diferencia hay entre agregación y composición?",
  "@IA no me acuerdo qué es un atributo derivado",
  "@IA revisá las relaciones del diagrama, ¿están bien las cardinalidades?",
];

const initials = (name = "") =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("") || "?";

function formatTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === now.toDateString()
    ? hm
    : `${d.toLocaleDateString([], { day: "2-digit", month: "2-digit" })} ${hm}`;
}

function Avatar({ name, color, size = 26, title }) {
  return (
    <div
      title={title || name}
      style={{
        width: size,
        height: size,
        flex: "none",
        borderRadius: 999,
        display: "grid",
        placeItems: "center",
        background: color,
        color: "#fff",
        fontSize: size * 0.4,
        fontWeight: 700,
        border: "2px solid var(--surface-1)",
      }}
    >
      {initials(name)}
    </div>
  );
}

function ChatMessage({ m, mine, canDecide, onDecide }) {
  const time = <span className="text-muted" style={{ fontSize: 11 }}>{formatTime(m.created_at)}</span>;

  // ---- Respuesta (o error) de la IA ----
  if (m.role !== "USER") {
    const isError = m.role === "ERROR";
    const nActions = m.actions?.length || 0;
    return (
      <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "flex-start", maxWidth: "94%" }}>
        <div
          style={{
            width: 26, height: 26, flex: "none", borderRadius: 999, display: "grid", placeItems: "center",
            background: isError ? "var(--danger-soft)" : "var(--accent-soft)",
            color: isError ? "var(--danger)" : "var(--accent)",
          }}
        >
          <Icon name={isError ? "warning" : "sparkles"} size={14} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap", marginBottom: 2 }}>
            <strong style={{ fontSize: 12, color: isError ? "var(--danger)" : "var(--accent)" }}>
              {m.author_name}
            </strong>
            {m.ai_model_label && (
              <span style={{ fontSize: 10, color: "var(--text-muted)" }} title="Modelo que generó la respuesta">
                · {m.ai_model_label}
              </span>
            )}
            {m.addressed_to_name && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                responde a <strong style={{ color: "var(--text)" }}>@{m.addressed_to_name}</strong>
              </span>
            )}
            {time}
          </div>
          <div
            style={{
              padding: "var(--sp-2) var(--sp-3)",
              borderRadius: "var(--radius)",
              fontSize: 13,
              lineHeight: 1.45,
              background: isError ? "var(--danger-soft)" : "var(--surface-2)",
              color: isError ? "var(--danger)" : "var(--text)",
              border: `1px solid ${isError ? "var(--danger)" : "var(--accent-soft)"}`,
            }}
          >
            {m.ai_mode === "MENTOR" && !isError && (
              <div
                style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--accent)", marginBottom: 4 }}
                title="Respuesta del asesor: la IA no modificó el diagrama"
              >
                <Icon name="help" size={11} />
                {m.proposal ? "Asesor · propone, no modifica el diagrama" : "Mentoría · no modifica el diagrama"}
              </div>
            )}
            <ChatMarkdown text={m.content} />
            {m.proposal && (
              <ProposalCard proposal={m.proposal} canDecide={canDecide(m.proposal)} onDecide={onDecide} />
            )}
            {nActions > 0 && (
              <div
                style={{
                  marginTop: 6, display: "inline-flex", alignItems: "center", gap: 4,
                  fontSize: 11, color: "var(--success)",
                }}
              >
                <Icon name="check" size={12} />
                Aplicó {nActions} {nActions === 1 ? "cambio" : "cambios"} en el diagrama
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ---- Mensaje de un colaborador ----
  const color = colorFor(m.author_email);
  return (
    <div
      style={{
        display: "flex",
        gap: "var(--sp-2)",
        alignItems: "flex-start",
        alignSelf: mine ? "flex-end" : "flex-start",
        flexDirection: mine ? "row-reverse" : "row",
        maxWidth: "88%",
      }}
    >
      {!mine && <Avatar name={m.author_name} color={color} />}
      <div style={{ minWidth: 0, display: "grid", justifyItems: mine ? "end" : "start" }}>
        <div style={{ display: "flex", gap: 6, alignItems: "baseline", marginBottom: 2 }}>
          {!mine && <strong style={{ fontSize: 12, color }}>{m.author_name}</strong>}
          {mine && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Vos</span>}
          {time}
        </div>
        <div
          style={{
            padding: "var(--sp-2) var(--sp-3)",
            borderRadius: "var(--radius)",
            fontSize: 13,
            lineHeight: 1.45,
            ...(mine
              ? { background: "var(--accent)", color: "var(--accent-text)" }
              : { background: "var(--surface-2)", color: "var(--text)" }),
          }}
        >
          {m.asks_ai && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, opacity: 0.85, marginBottom: 2 }}>
              <Icon name="sparkles" size={11} />
              Pregunta a la IA
            </div>
          )}
          <ChatMarkdown text={m.content} markdown={false} />
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({ diagramId, myEmail, isOwner = false, aiSolutionsEnabled = false }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [aiMode, setAiMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState(null);
  const [aiSettings, setAiSettings] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  const chat = useTeamChat(diagramId, { myEmail, isOpen: open });
  const { messages, pendingAi, presence } = chat;
  const pendingList = useMemo(() => Object.entries(pendingAi), [pendingAi]);

  const voice = useVoiceRecorder({
    // El dictado se deja en el cuadro de texto (no se envía solo) para que la
    // persona lo revise antes de mandarlo al equipo; va dirigido a la IA.
    onTranscript: (t) => {
      setText((prev) => (prev ? `${prev} ${t}` : t));
      setAiMode(true);
      inputRef.current?.focus();
    },
    onError: setNotice,
  });

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [open, messages.length, pendingList.length]);

  const aiEnabled = aiSettings?.enabled !== false;
  const willAskAi = aiEnabled && (aiMode || hasAiMention(text));
  // Una propuesta la decide quien hizo la consulta o el dueño del diagrama.
  const canDecide = (p) => p.status === "proposed" && (isOwner || p.requested_by_email === myEmail);

  const submit = async (value = text) => {
    const v = value.trim();
    if (!v || sending) return;
    setSending(true);
    setNotice(null);
    try {
      await chat.send(v, { askAi: aiMode && !hasAiMention(v) });
      setText("");
      setAiMode(false);
    } catch (err) {
      setNotice(err?.response?.data?.detail?.toString?.() || "No se pudo enviar el mensaje.");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
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
        title="Chat del equipo y asistente de IA"
      >
        <Icon name="chat" size={18} />
        Chat del equipo
        {pendingList.length > 0 && <Icon name="sparkles" size={14} className="spinning" />}
        {chat.unread > 0 && (
          <span
            style={{
              minWidth: 20, height: 20, padding: "0 6px", borderRadius: 999,
              background: "var(--danger)", color: "#fff", fontSize: 11, fontWeight: 700,
              display: "grid", placeItems: "center",
            }}
          >
            {chat.unread > 99 ? "99+" : chat.unread}
          </span>
        )}
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
        top: "var(--sp-4)",
        width: 380,
        maxWidth: "calc(100% - 2 * var(--sp-4))",
        display: "flex",
        flexDirection: "column",
        boxShadow: "var(--shadow-lg)",
        zIndex: "var(--z-float)",
        overflow: "hidden",
      }}
    >
      {/* Encabezado: título + quién está conectado */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
          padding: "var(--sp-3) var(--sp-4)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Icon name="chat" size={16} style={{ color: "var(--accent)" }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <strong style={{ fontSize: 13 }}>Chat del equipo</strong>
          <div className="text-muted" style={{ fontSize: 11 }}>
            {presence.length === 0
              ? "Conectando…"
              : `${presence.length} ${presence.length === 1 ? "conectado" : "conectados"}: ${presence
                  .map((p) => (p.email === myEmail ? "vos" : p.name.split(" ")[0]))
                  .join(", ")}`}
          </div>
        </div>
        <div style={{ display: "flex" }}>
          {presence.slice(0, 4).map((p, i) => (
            <div key={p.email} style={{ marginLeft: i ? -8 : 0 }}>
              <Avatar name={p.name} color={p.color} size={24} title={`${p.name} (${p.email})`} />
            </div>
          ))}
        </div>
        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setOpen(false)} title="Cerrar">
          <Icon name="close" size={15} />
        </button>
      </div>

      <AiSettingsBar
        diagramId={diagramId}
        isOwner={isOwner}
        initialEnabled={aiSolutionsEnabled}
        onChange={setAiSettings}
      />

      {/* Conversación */}
      <div
        className="scroll"
        style={{ flex: 1, padding: "var(--sp-4)", display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}
      >
        {chat.hasMore && (
          <button className="btn btn-sm btn-ghost" style={{ alignSelf: "center" }} onClick={chat.loadOlder}>
            Cargar mensajes anteriores
          </button>
        )}

        {chat.loading && messages.length === 0 && (
          <div className="text-muted" style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
            <Icon name="loader" size={14} className="spinning" /> Cargando conversación…
          </div>
        )}
        {chat.loadError && (
          <div style={{ fontSize: 12, color: "var(--danger)" }}>{chat.loadError}</div>
        )}

        {!chat.loading && messages.length === 0 && (
          <div style={{ display: "grid", gap: "var(--sp-3)" }}>
            <p className="text-muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>
              Conversá con tu equipo en tiempo real. Para consultar al asistente escribí{" "}
              <strong>@IA</strong> al principio del mensaje: edita el diagrama cuando se lo pedís, y
              como asesor revisa el modelo, explica conceptos de diseño y deja <strong>propuestas</strong>{" "}
              de cambios que quien preguntó (o el dueño) puede aplicar con un botón. La pregunta y la
              respuesta las ve todo el equipo, y la IA te responde a vos por tu nombre.
            </p>
            <div style={{ display: "grid", gap: "var(--sp-2)" }}>
              {SUGERENCIAS.map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setText(s);
                    inputRef.current?.focus();
                  }}
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
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <ChatMessage
            key={m.id}
            m={m}
            mine={m.role === "USER" && m.author_email === myEmail}
            canDecide={canDecide}
            onDecide={chat.decide}
          />
        ))}

        {pendingList.map(([reqId, p]) => (
          <div
            key={reqId}
            className="text-muted"
            style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", fontSize: 12 }}
          >
            <Icon name="loader" size={14} className="spinning" />
            La IA está respondiendo a {p.name}…
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {notice && (
        <div
          style={{
            margin: "0 var(--sp-3)",
            padding: "var(--sp-2) var(--sp-3)",
            borderRadius: "var(--radius)",
            background: "var(--danger-soft)",
            color: "var(--danger)",
            fontSize: 12,
            display: "flex",
            gap: 6,
            alignItems: "flex-start",
          }}
        >
          <Icon name="warning" size={13} />
          <span style={{ flex: 1 }}>{notice}</span>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setNotice(null)} title="Cerrar aviso">
            <Icon name="close" size={12} />
          </button>
        </div>
      )}

      {/* Entrada */}
      <div style={{ padding: "var(--sp-3)", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
        <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "flex-end" }}>
          <textarea
            ref={inputRef}
            className="input"
            rows={1}
            value={text}
            maxLength={4000}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={
              voice.listening
                ? "Grabando… tocá el micrófono para terminar"
                : voice.transcribing
                ? "Transcribiendo…"
                : willAskAi
                ? "Preguntale algo a la IA…"
                : "Mensaje, o @IA para el asistente"
            }
            disabled={sending || voice.transcribing}
            style={{ resize: "none", minHeight: 36, maxHeight: 120, height: "auto", lineHeight: 1.4, paddingTop: 8 }}
          />
          <button
            className={`btn btn-icon ${willAskAi ? "btn-active" : ""}`}
            onClick={() => setAiMode((v) => !v)}
            disabled={sending || hasAiMention(text) || !aiEnabled}
            title={!aiEnabled ? "El asesor IA está desactivado en este diagrama" : willAskAi ? "El mensaje se enviará a la IA" : "Preguntarle a la IA"}
            aria-pressed={willAskAi}
          >
            <Icon name="sparkles" />
          </button>
          <button
            className={`btn btn-icon ${voice.listening ? "btn-active" : ""}`}
            onClick={voice.toggle}
            disabled={sending || voice.transcribing}
            title={voice.listening ? "Detener grabación" : "Dictar por voz"}
          >
            <Icon name={voice.transcribing ? "loader" : "mic"} className={voice.transcribing ? "spinning" : ""} />
          </button>
          <button
            className="btn btn-primary btn-icon"
            onClick={() => submit()}
            disabled={sending || !text.trim()}
            title="Enviar"
          >
            <Icon name={sending ? "loader" : "send"} className={sending ? "spinning" : ""} />
          </button>
        </div>
        <div className="text-muted" style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
          {!aiEnabled ? (
            <>
              <Icon name="lock" size={11} />
              El asesor IA está desactivado en este diagrama
            </>
          ) : willAskAi ? (
            <>
              <Icon name="sparkles" size={11} style={{ color: "var(--accent)" }} />
              Pregunta a la IA · todo el equipo verá la pregunta y la respuesta
            </>
          ) : (
            <>Enter para enviar · Shift+Enter para salto de línea</>
          )}
        </div>
      </div>
    </div>
  );
}
