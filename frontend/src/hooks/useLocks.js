// src/hooks/useLocks.js
//
// Exclusión mutua a nivel de clase. Se suscribe a los eventos de lock que
// manda el backend por WebSocket y expone lockClass/unlockClass para
// pedir/soltar el bloqueo. El backend es la única autoridad: acá solo se
// refleja lo que él confirma (class.locked/class.unlocked), nunca se marca
// nada como bloqueado de forma optimista en el cliente.
//
// "Es mío" se decide por conn_id (la conexión), no por email: dos pestañas
// de la misma persona logueada tienen el mismo email pero conexiones
// distintas, y ese es justo el caso que la exclusión mutua tiene que
// distinguir (si compararas por email, una persona con dos pestañas nunca
// se bloquearía a sí misma).

import { useEffect, useRef } from "react";
import { getConnId, onEvent, requestLock, releaseLock } from "../api/realtime";
import useLocks from "../store/locks";

export default function useLocksSync(diagramId, onDenied) {
  const setSnapshot = useLocks((s) => s.setSnapshot);
  const setLocked = useLocks((s) => s.setLocked);
  const setUnlocked = useLocks((s) => s.setUnlocked);
  const clear = useLocks((s) => s.clear);
  const onDeniedRef = useRef(onDenied);
  onDeniedRef.current = onDenied;

  useEffect(() => {
    if (!diagramId) return;

    const offs = [
      onEvent("locks.snapshot", (map) => setSnapshot(map)),
      onEvent("class.locked", ({ class_id, email, conn_id }) => setLocked(class_id, email, conn_id)),
      onEvent("class.unlocked", ({ class_id }) => setUnlocked(class_id)),
      onEvent("lock.denied", ({ class_id, locked_by }) => onDeniedRef.current?.(class_id, locked_by)),
    ];

    return () => {
      offs.forEach((off) => off());
      clear();
    };
  }, [diagramId, setSnapshot, setLocked, setUnlocked, clear]);

  const byClass = useLocks((s) => s.byClass);

  /** true si otra CONEXIÓN (no la mía) tiene bloqueada esa clase. */
  const isLockedByOther = (classId) => {
    const lock = byClass[classId];
    if (!lock) return false;
    return lock.connId !== getConnId();
  };

  const lockOwner = (classId) => byClass[classId]?.email || null;

  return {
    lockClass: requestLock,
    unlockClass: releaseLock,
    isLockedByOther,
    lockOwner,
  };
}
