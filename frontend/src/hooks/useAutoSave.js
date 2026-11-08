// src/hooks/useAutoSave.js
//
// Guardado automático con estado visible.
//
// La herramienta no tiene botón "Guardar": cada cambio se persiste solo.
// Para que eso sea confiable hace falta (a) no mandar una petición por cada
// tecla y (b) que el usuario vea si se guardó o si falló -- antes un error
// del servidor (por ejemplo un nombre repetido) se descartaba en silencio y
// parecía que el cambio se había aplicado.

import { useCallback, useEffect, useRef, useState } from "react";

export default function useAutoSave(delay = 600) {
  const [status, setStatus] = useState("idle"); // idle | saving | saved | error
  const [error, setError] = useState("");
  const timer = useRef(null);
  const resetTimer = useRef(null);
  const alive = useRef(true);

  useEffect(() => {
    // Resetear acá (no alcanza con `useRef(true)` en la declaración): en
    // StrictMode React monta, desmonta y vuelve a montar cada componente al
    // arrancar, y si el segundo montaje reusa el mismo ref ya marcado como
    // "muerto" por el cleanup del primero, cualquier guardado agendado justo
    // después se descartaba en silencio sin avisar ni al usuario ni a la
    // consola -- el checkbox se veía tildado pero nunca llegaba al backend.
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  /** Agenda `fn` (async). Las llamadas seguidas reemplazan a la anterior. */
  const save = useCallback(
    (fn) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(async () => {
        if (!alive.current) return;
        setStatus("saving");
        setError("");
        try {
          await fn();
          if (!alive.current) return;
          setStatus("saved");
          if (resetTimer.current) clearTimeout(resetTimer.current);
          resetTimer.current = setTimeout(() => alive.current && setStatus("idle"), 1600);
        } catch (e) {
          if (!alive.current) return;
          setError(e?.response?.data?.detail || "No se pudo guardar el cambio");
          setStatus("error");
        }
      }, delay);
    },
    [delay]
  );

  return { save, status, error };
}
