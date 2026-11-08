// src/store/undo.js
//
// Pila de deshacer (Ctrl+Z).
//
// Cada acción que modifica el diagrama registra acá cómo revertirse. El
// "deshacer" no toca el estado local a mano: ejecuta la operación inversa
// contra la misma API que todo lo demás, así el cambio también se emite por
// WebSocket y el resto de los usuarios ve la reversión igual que cualquier
// otra edición. Eso es importante porque el editor es colaborativo.
//
// Alcance a propósito: sólo se deshacen las acciones estructurales que hizo
// este usuario en esta sesión (crear/mover/redimensionar/eliminar clases,
// agregar/quitar atributos y métodos, crear/eliminar relaciones). La edición
// de texto letra por letra no se apila: deshacerla tecla a tecla sería más
// molesto que útil, y esos campos ya se corrigen escribiendo encima.

import { create } from "zustand";

const LIMITE = 50;

const useUndo = create((set, get) => ({
  stack: [],
  running: false,

  /**
   * Registra una acción reversible.
   * @param {string} label descripción corta, ej. "crear clase Cliente"
   * @param {() => Promise<void>} undo operación inversa
   */
  push: (label, undo) =>
    set((s) => ({
      // Si se está ejecutando un deshacer, no registramos su propio efecto:
      // si no, deshacer volvería a apilarse y quedaría en un ida y vuelta.
      stack: s.running ? s.stack : [...s.stack, { label, undo }].slice(-LIMITE),
    })),

  /** Ejecuta el último deshacer. Devuelve su etiqueta, o null si no había nada. */
  undoLast: async () => {
    const { stack, running } = get();
    if (running || stack.length === 0) return null;

    const last = stack[stack.length - 1];
    set({ stack: stack.slice(0, -1), running: true });
    try {
      await last.undo();
      return last.label;
    } finally {
      set({ running: false });
    }
  },

  clear: () => set({ stack: [] }),
}));

export default useUndo;
