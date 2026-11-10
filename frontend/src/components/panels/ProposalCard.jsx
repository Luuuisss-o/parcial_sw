// src/components/panels/ProposalCard.jsx
//
// Propuesta de cambios del asesor IA (segundo parcial, CU-06 / CU-07).
//
// El asesor nunca modifica el diagrama por su cuenta: cuando su
// recomendación implica cambios concretos, los deja como PROPUESTA debajo de
// su respuesta. Todos la ven; la aplica o la rechaza quien hizo la consulta o
// el dueño del diagrama. Si las clases involucradas cambiaron desde que se
// propuso, el servidor la marca "desactualizada" en vez de aplicarla a ciegas.

import { useState } from "react";
import Icon from "../common/Icon";

const STATUS = {
  proposed: { label: "Pendiente de revisión", color: "var(--accent)", icon: "sparkles" },
  applying: { label: "Aplicando…", color: "var(--accent)", icon: "loader" },
  applied: { label: "Aplicada", color: "var(--success)", icon: "check" },
  rejected: { label: "Rechazada", color: "var(--text-muted)", icon: "close" },
  stale: { label: "Desactualizada", color: "var(--danger)", icon: "warning" },
  failed: { label: "Falló al aplicarse", color: "var(--danger)", icon: "warning" },
};

export default function ProposalCard({ proposal: p, canDecide, onDecide }) {
  const [busy, setBusy] = useState(null); // "accept" | "reject"
  const [error, setError] = useState(null);
  const st = STATUS[p.status] || STATUS.proposed;
  const pending = p.status === "proposed";

  const decide = async (accept) => {
    setBusy(accept ? "accept" : "reject");
    setError(null);
    try {
      await onDecide(p.id, accept);
    } catch (err) {
      setError(err?.response?.data?.detail?.toString?.() || "No se pudo completar la acción.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      style={{
        marginTop: 8, padding: "var(--sp-2) var(--sp-3)", borderRadius: "var(--radius)",
        border: `1px dashed ${pending ? "var(--accent)" : "var(--border)"}`, background: "var(--surface-1)",
        display: "grid", gap: 6, fontSize: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <Icon name="sparkles" size={12} style={{ color: "var(--accent)" }} />
        <strong style={{ flex: 1 }}>Propuesta de cambios</strong>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color: st.color, fontSize: 11 }}>
          <Icon name={st.icon} size={11} className={p.status === "applying" ? "spinning" : ""} />
          {st.label}
        </span>
      </div>
      <div style={{ color: "var(--text)" }}>{p.summary}</div>
      <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 2 }}>
        {p.changes.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>

      {(p.status === "stale" || p.status === "failed") && p.result?.length > 0 && (
        <div style={{ color: "var(--danger)", display: "grid", gap: 2 }}>
          {p.result.filter((r) => !r.ok).map((r, i) => (
            <span key={i}>{r.message}</span>
          ))}
        </div>
      )}

      {pending && canDecide && (
        <div style={{ display: "flex", gap: "var(--sp-2)" }}>
          <button className="btn btn-primary btn-sm" onClick={() => decide(true)} disabled={!!busy}
            title="Aplica estos cambios al diagrama para todo el equipo">
            <Icon name={busy === "accept" ? "loader" : "check"} size={12} className={busy === "accept" ? "spinning" : ""} />
            Aplicar
          </button>
          <button className="btn btn-sm" onClick={() => decide(false)} disabled={!!busy}>
            <Icon name={busy === "reject" ? "loader" : "close"} size={12} className={busy === "reject" ? "spinning" : ""} />
            Rechazar
          </button>
        </div>
      )}
      {pending && !canDecide && (
        <span className="text-muted" style={{ fontSize: 11 }}>
          La puede aplicar o rechazar {p.requested_by_name || "quien preguntó"} o el dueño del diagrama.
        </span>
      )}
      {!pending && p.decided_by_name && (
        <span className="text-muted" style={{ fontSize: 11 }}>
          {p.status === "rejected" ? "Rechazada" : "Decidida"} por {p.decided_by_name}
        </span>
      )}
      {error && <span style={{ color: "var(--danger)" }}>{error}</span>}
    </div>
  );
}
