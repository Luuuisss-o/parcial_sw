// src/hooks/useTeamChat.js
//
// Estado del chat grupal del diagrama (Fase 2):
//   - historial persistido (GET /chat) + mensajes nuevos por WebSocket,
//     fusionados sin duplicados y ordenados por `seq` (orden del servidor,
//     idéntico para todo el equipo aunque un mensaje llegue antes que el
//     historial);
//   - quién está conectado (evento `presence`);
//   - consultas a la IA en curso de CUALQUIER colaborador (ai.started →
//     ai.done/ai.error, identificadas por request_id), para mostrar
//     "La IA está respondiendo a Ana…" a todos;
//   - contador de no leídos mientras el panel está cerrado.

import { useCallback, useEffect, useRef, useState } from "react";
import { decideProposal, listChat, sendChat } from "../api/chat";
import { getPresence, onEvent } from "../api/realtime";

const PAGE = 50;

// Consultas a la IA que todavía no tienen respuesta según el historial
// (ai_status persistido): quien entra tarde también ve "La IA está
// respondiendo a…", no solo quien estaba conectado cuando empezó.
function pendingFromHistory(items) {
  const answered = new Set(items.filter((m) => m.reply_to_id).map((m) => m.reply_to_id));
  const out = {};
  for (const m of items) {
    if (m.asks_ai && ["pending", "running", "device"].includes(m.ai_status) && !answered.has(m.id)) {
      out[m.id] = { name: m.author_name, text: m.content };
    }
  }
  return out;
}

function mergeMessages(prev, incoming) {
  const byId = new Map(prev.map((m) => [m.id, m]));
  for (const m of incoming) byId.set(m.id, m);
  return [...byId.values()].sort((a, b) => a.seq - b.seq);
}

export default function useTeamChat(diagramId, { myEmail, isOpen }) {
  const [messages, setMessages] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [presence, setPresence] = useState(() => getPresence());
  const [pendingAi, setPendingAi] = useState({}); // request_id -> {name, text}
  const [unread, setUnread] = useState(0);
  const isOpenRef = useRef(isOpen);
  const seenIds = useRef(new Set()); // ids ya recibidos (historial o socket)

  useEffect(() => {
    isOpenRef.current = isOpen;
    if (isOpen) setUnread(0);
  }, [isOpen]);

  // ---- Historial inicial ----
  useEffect(() => {
    if (!diagramId) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    listChat(diagramId, { limit: PAGE })
      .then((data) => {
        if (cancelled) return;
        data.items.forEach((m) => seenIds.current.add(m.id));
        setMessages((prev) => mergeMessages(prev, data.items));
        setHasMore(data.has_more);
        setPendingAi((p) => ({ ...pendingFromHistory(data.items), ...p }));
      })
      .catch(() => !cancelled && setLoadError("No se pudo cargar el historial del chat."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [diagramId]);

  // ---- Tiempo real ----
  useEffect(() => {
    if (!diagramId) return;
    setPresence(getPresence());
    const offs = [
      // Tras reconectar: traer los mensajes que llegaron mientras no había
      // conexión (mergeMessages descarta los repetidos por id).
      onEvent("reconnected", () => {
        listChat(diagramId, { limit: PAGE })
          .then((data) => {
            data.items.forEach((m) => seenIds.current.add(m.id));
            setMessages((prev) => mergeMessages(prev, data.items));
            setPendingAi(pendingFromHistory(data.items));
          })
          .catch(() => {});
      }),
      // Una propuesta del asesor cambió de estado (la aceptó/rechazó alguien):
      // se actualiza su tarjeta en todas las sesiones.
      onEvent("ai.proposal", (p) => {
        if (!p?.id) return;
        setMessages((prev) => prev.map((m) => (m.proposal?.id === p.id ? { ...m, proposal: p } : m)));
      }),
      onEvent("chat.message", (msg) => {
        if (!msg || msg.diagram_id !== diagramId || seenIds.current.has(msg.id)) return;
        seenIds.current.add(msg.id);
        const mine = msg.role === "USER" && msg.author_email === myEmail;
        if (!isOpenRef.current && !mine) setUnread((n) => n + 1);
        setMessages((prev) => mergeMessages(prev, [msg]));
      }),
      onEvent("presence", (list) => setPresence(Array.isArray(list) ? list : [])),
      onEvent("ai.started", (d) => {
        if (!d?.request_id) return;
        setPendingAi((p) => ({
          ...p,
          [d.request_id]: { name: d.requested_by?.name || "alguien", text: d.text },
        }));
      }),
      ...["ai.done", "ai.error"].map((ev) =>
        onEvent(ev, (d) => {
          if (!d?.request_id) return;
          setPendingAi((p) => {
            const next = { ...p };
            delete next[d.request_id];
            return next;
          });
        })
      ),
    ];
    return () => offs.forEach((off) => off());
  }, [diagramId, myEmail]);

  const loadOlder = useCallback(async () => {
    const oldest = messages[0];
    if (!oldest) return;
    const data = await listChat(diagramId, { limit: PAGE, beforeSeq: oldest.seq });
    data.items.forEach((m) => seenIds.current.add(m.id));
    setMessages((prev) => mergeMessages(prev, data.items));
    setHasMore(data.has_more);
  }, [diagramId, messages]);

  const send = useCallback(
    async (text, { askAi = false } = {}) => {
      const msg = await sendChat(diagramId, text, { askAi });
      // Normalmente el WebSocket ya lo trajo; si no (socket caído), igual se ve.
      seenIds.current.add(msg.id);
      setMessages((prev) => mergeMessages(prev, [msg]));
      return msg;
    },
    [diagramId]
  );

  const decide = useCallback(
    async (proposalId, accept) => {
      const p = await decideProposal(diagramId, proposalId, accept);
      setMessages((prev) => prev.map((m) => (m.proposal?.id === p.id ? { ...m, proposal: p } : m)));
      return p;
    },
    [diagramId]
  );

  return { messages, hasMore, loading, loadError, presence, pendingAi, unread, loadOlder, send, decide };
}
