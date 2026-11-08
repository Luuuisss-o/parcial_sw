// src/store/locks.js
//
// Exclusion mutua: quien tiene bloqueada cada clase ahora mismo. Se llena
// solo con los eventos que manda el backend por WebSocket (locks.snapshot al
// conectar, class.locked / class.unlocked en vivo); este store nunca decide
// nada por su cuenta, solo refleja lo que el servidor autorizo.
//
// Cada lock guarda {email, connId}: el email es para mostrar en pantalla
// ("lo está editando fulano@..."), pero para decidir si el lock es MIO hay
// que comparar por connId, no por email -- dos pestañas del mismo usuario
// (o dos personas que comparten un login) tienen el mismo email pero
// conexiones distintas, y son justo el caso que la exclusión mutua tiene
// que distinguir.

import { create } from "zustand";

const useLocks = create((set) => ({
  // { classId: {email, connId} }
  byClass: {},

  setSnapshot: (map) => set({ byClass: { ...(map || {}) } }),

  setLocked: (classId, email, connId) =>
    set((s) => ({ byClass: { ...s.byClass, [classId]: { email, connId } } })),

  setUnlocked: (classId) =>
    set((s) => {
      if (!(classId in s.byClass)) return s;
      const next = { ...s.byClass };
      delete next[classId];
      return { byClass: next };
    }),

  clear: () => set({ byClass: {} }),
}));

export default useLocks;
