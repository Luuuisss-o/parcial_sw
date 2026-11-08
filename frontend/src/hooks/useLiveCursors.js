// src/hooks/useLiveCursors.js
//
// Cursores en vivo de los demás colaboradores del diagrama, al estilo
// Miro/Figma: cada pestaña manda su posición de mouse por WebSocket (en
// coordenadas del "mundo" del diagrama, no de pantalla, porque cada
// participante puede tener su propio pan/zoom) y este hook arma el estado
// de todos los cursores ajenos para dibujarlos encima del lienzo.
//
// El envío está limitado a ~20/s (throttle) para no saturar el socket: la
// posición del mouse cambia mucho más seguido de lo que hace falta para
// que el movimiento se vea fluido en la pantalla de otro.
//
// Un cursor se borra al recibir "cursor.left" (la pestaña dueña lo mandó
// al salir del lienzo o desconectarse) o, como red de seguridad, si no
// hubo noticias de él en varios segundos -- por si el cierre del navegador
// fue tan abrupto que ni el evento de desconexión llegó a tiempo.

import { useEffect, useRef, useState } from "react";
import { onEvent, sendCursor, sendCursorLeft } from "../api/realtime";

const SEND_THROTTLE_MS = 50; // ~20 actualizaciones por segundo
const STALE_MS = 8000; // limpieza de respaldo si nunca llegó cursor.left

export default function useLiveCursors(diagramId) {
  const [cursors, setCursors] = useState({}); // { conn_id: {name, color, x, y, label, lastSeen} }
  const lastSentRef = useRef(0);

  useEffect(() => {
    if (!diagramId) return;

    const offs = [
      onEvent("cursor.move", (data) => {
        setCursors((prev) => ({
          ...prev,
          [data.conn_id]: { ...data, lastSeen: Date.now() },
        }));
      }),
      onEvent("cursor.left", ({ conn_id }) => {
        setCursors((prev) => {
          if (!(conn_id in prev)) return prev;
          const next = { ...prev };
          delete next[conn_id];
          return next;
        });
      }),
    ];

    // Red de seguridad: si un cursor no manda nada en STALE_MS, lo saco
    // igual (cierre abrupto de pestaña, pérdida de red, etc).
    const interval = setInterval(() => {
      setCursors((prev) => {
        const now = Date.now();
        const next = {};
        let changed = false;
        for (const [id, c] of Object.entries(prev)) {
          if (now - c.lastSeen < STALE_MS) next[id] = c;
          else changed = true;
        }
        return changed ? next : prev;
      });
    }, 2000);

    return () => {
      offs.forEach((off) => off());
      clearInterval(interval);
      setCursors({});
      sendCursorLeft();
    };
  }, [diagramId]);

  /** Reporta mi posición (coordenadas del mundo del diagrama), con throttle. */
  const reportCursor = (x, y, label) => {
    const now = Date.now();
    if (now - lastSentRef.current < SEND_THROTTLE_MS) return;
    lastSentRef.current = now;
    sendCursor(x, y, label);
  };

  return { cursors: Object.values(cursors), reportCursor };
}
