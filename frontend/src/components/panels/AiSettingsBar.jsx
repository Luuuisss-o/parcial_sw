// src/components/panels/AiSettingsBar.jsx
//
// Franja del chat que muestra cómo está configurada la IA del diagrama.
// Pedido del docente (Fase 2): "la IA va a tener la capacidad de entregar
// soluciones cuando así se lo requieran. Eso va a ser configurable".
//
// Todo el equipo ve el estado; solo el dueño del diagrama puede cambiarlo.
// Cuando el dueño lo cambia, el backend avisa por WebSocket (`ai.settings`)
// y la franja se actualiza en todas las sesiones abiertas.

import { useEffect, useState } from "react";
import { getAiSettings, updateAiSettings } from "../../api/chat";
import { onEvent } from "../../api/realtime";
import Icon from "../common/Icon";

export default function AiSettingsBar({ diagramId, isOwner, initialEnabled = false }) {
  const [enabled, setEnabled] = useState(initialEnabled);
  const [saving, setSaving] = useState(false);
  const [changedBy, setChangedBy] = useState(null);

  useEffect(() => {
    let alive = true;
    getAiSettings(diagramId)
      .then((s) => alive && setEnabled(!!s.solutions_enabled))
      .catch(() => {});
    const off = onEvent("ai.settings", (s) => {
      setEnabled(!!s?.solutions_enabled);
      setChangedBy(s?.changed_by || null);
    });
    return () => {
      alive = false;
      off();
    };
  }, [diagramId]);

  const toggle = async () => {
    if (!isOwner || saving) return;
    setSaving(true);
    try {
      const s = await updateAiSettings(diagramId, { solutions_enabled: !enabled });
      setEnabled(!!s.solutions_enabled);
      setChangedBy(null);
    } catch {
      /* el estado no cambia: el switch vuelve a mostrar el valor real */
    } finally {
      setSaving(false);
    }
  };

  const label = enabled
    ? "La IA puede entregar soluciones de diseño completas"
    : "La IA solo hace ediciones puntuales y mentoría";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-2)",
        padding: "6px var(--sp-4)",
        borderBottom: "1px solid var(--border)",
        background: enabled ? "var(--accent-soft)" : "var(--surface-2)",
        fontSize: 11,
      }}
    >
      <Icon name="sparkles" size={12} style={{ color: enabled ? "var(--accent)" : "var(--text-muted)", flex: "none" }} />
      <span style={{ flex: 1, minWidth: 0, color: "var(--text)" }}>
        {label}
        {changedBy && <span className="text-muted"> · cambiado por {changedBy}</span>}
      </span>
      {isOwner ? (
        <button
          role="switch"
          aria-checked={enabled}
          aria-label="La IA puede entregar soluciones"
          onClick={toggle}
          disabled={saving}
          title={enabled ? "Desactivar entrega de soluciones" : "Permitir que la IA entregue soluciones"}
          style={{
            flex: "none",
            width: 32,
            height: 18,
            borderRadius: 999,
            border: "none",
            padding: 2,
            cursor: saving ? "wait" : "pointer",
            background: enabled ? "var(--accent)" : "var(--border-strong)",
            display: "flex",
            justifyContent: enabled ? "flex-end" : "flex-start",
            transition: "background .15s",
          }}
        >
          <span style={{ width: 14, height: 14, borderRadius: 999, background: "#fff", display: "block" }} />
        </button>
      ) : (
        <span className="text-muted" title="Solo el dueño del diagrama puede cambiarlo" style={{ flex: "none" }}>
          <Icon name="lock" size={11} />
        </span>
      )}
    </div>
  );
}
