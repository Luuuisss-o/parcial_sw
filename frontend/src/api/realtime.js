import { WS_URL } from "../config";
import { getToken } from "../store/auth";

// Canal WebSocket del diagrama: por acá llegan los cambios que hacen los
// demás usuarios, el progreso del asistente de IA, y el estado de
// exclusión mutua (qué clase está bloqueada y por quién).
//
// Los listeners viven aparte del socket a propósito: antes `connect()` los
// borraba a todos, así que cualquier componente que se suscribiera antes de
// que se abriera la conexión (por el orden en que React corre los efectos)
// se quedaba sin recibir nada.

let socket = null;
let currentDiagramId = null;
let myConnId = null; // id de ESTA conexion, para distinguir mis locks de los de otra pestaña/persona
const listeners = new Map(); // event -> Set<callback>
// Último snapshot de presencia ("quién está conectado"): el backend lo manda
// una sola vez al entrar alguien, y el panel de chat puede montarse después
// de ese mensaje, así que se guarda para poder leerlo en cualquier momento.
let lastPresence = [];

function emit(event, data) {
  const subs = listeners.get(event);
  if (!subs) return;
  for (const cb of subs) {
    try {
      cb(data);
    } catch (err) {
      console.error(`[realtime] error en listener de "${event}":`, err);
    }
  }
}

export function connect(diagramId) {
  // Ya conectados a este mismo diagrama: no reabrir.
  if (socket && currentDiagramId === diagramId && socket.readyState <= WebSocket.OPEN) {
    return;
  }

  closeSocket();
  currentDiagramId = diagramId;
  myConnId = null;
  lastPresence = [];
  // El WebSocket nativo del navegador no permite mandar headers custom
  // (no hay forma de poner Authorization ahí), así que el token viaja por
  // query string. El backend lo valida antes de aceptar la conexión.
  const token = getToken();
  socket = new WebSocket(`${WS_URL}/diagrams/${diagramId}/ws?token=${encodeURIComponent(token || "")}`);

  socket.onopen = () => console.log("[realtime] conectado al diagrama", diagramId);

  socket.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      console.warn("[realtime] mensaje no es JSON:", event.data);
      return;
    }
    // "connected" es interno: guarda el id de ESTA conexión (distinto por
    // pestaña, aunque sea el mismo usuario logueado) antes de reenviar
    // nada a los listeners, así isLockedByOther ya tiene con qué comparar.
    if (msg.event === "connected") {
      myConnId = msg.data?.conn_id ?? null;
      return;
    }
    if (msg.event === "presence") lastPresence = Array.isArray(msg.data) ? msg.data : [];
    emit(msg.event, msg.data);
  };

  socket.onclose = () => console.log("[realtime] conexión cerrada");
  socket.onerror = (e) => console.error("[realtime] error de conexión:", e);
}

function closeSocket() {
  if (!socket) return;
  // Un mensaje que ya estaba en vuelo para ESTA conexión puede llegar
  // después de decidir reemplazarla (típico con React StrictMode en
  // desarrollo, que monta/desmonta/remonta los efectos): sin desconectar
  // los cuatro handlers, ese "connected" tardío pisaba `myConnId` con el
  // id de la conexión vieja, y la pestaña terminaba viendo su propio lock
  // como si fuera de otra persona.
  socket.onopen = null;
  socket.onmessage = null;
  socket.onclose = null;
  socket.onerror = null;
  socket.close();
  socket = null;
}

export function disconnect() {
  closeSocket();
  currentDiagramId = null;
  lastPresence = [];
}

function send(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify(payload));
}

/** Pide el lock de exclusión mutua sobre una clase. */
export function requestLock(classId) {
  send({ action: "lock", class_id: classId });
}

/** Libera el lock de una clase (al deseleccionarla o salir del diagrama). */
export function releaseLock(classId) {
  send({ action: "unlock", class_id: classId });
}

/**
 * Avisa dónde está mi cursor, en coordenadas del "mundo" del diagrama (no
 * de pantalla: cada participante tiene su propio pan/zoom). `label` es
 * opcional y describe qué estoy haciendo (ej. "editando Cliente").
 */
export function sendCursor(x, y, label) {
  send({ action: "cursor", x, y, label });
}

/** Avisa que dejé de mover el mouse sobre el lienzo (se fue o cambió de pantalla). */
export function sendCursorLeft() {
  send({ action: "cursor_left" });
}

/** Usuarios conectados ahora al diagrama: [{user_id, name, email, color}]. */
export function getPresence() {
  return lastPresence;
}

/** El id de conexión que me asignó el backend (null hasta que llega). */
export function getConnId() {
  return myConnId;
}

/**
 * Suscribe un callback a un evento del diagrama.
 * @returns {() => void} función para darse de baja.
 */
export function onEvent(event, callback) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(callback);
  return () => {
    listeners.get(event)?.delete(callback);
  };
}
