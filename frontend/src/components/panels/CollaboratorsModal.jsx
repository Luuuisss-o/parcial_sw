// src/components/panels/CollaboratorsModal.jsx
//
// Gestión de colaboradores de un diagrama: solo el dueño puede invitar o
// sacar gente (el backend lo hace cumplir con un 404 si no sos el owner).
// Un colaborador invitado puede abrir el diagrama y editarlo en tiempo real
// junto con el resto -- es lo que hace que la herramienta sea colaborativa
// entre usuarios reales, no solo entre pestañas de la misma persona.

import { useEffect, useState } from "react";
import Icon from "../common/Icon";
import { listCollaborators, addCollaborator, removeCollaborator } from "../../api/diagrams";

export default function CollaboratorsModal({ diagram, isOwner, onClose }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await listCollaborators(diagram.id));
    } catch {
      setError("No se pudo cargar la lista de colaboradores");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [diagram.id]);

  const handleInvite = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setInviting(true);
    setError(null);
    try {
      await addCollaborator(diagram.id, email.trim());
      setEmail("");
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "No se pudo invitar a ese usuario");
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (userId) => {
    try {
      await removeCollaborator(diagram.id, userId);
      setItems((prev) => prev.filter((c) => c.user_id !== userId));
    } catch {
      setError("No se pudo quitar a ese colaborador");
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <div className="modal-header">
          <h2 className="modal-title">Colaboradores</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose} title="Cerrar">
            <Icon name="close" />
          </button>
        </div>

        <div className="modal-body scroll" style={{ display: "grid", gap: "var(--sp-3)" }}>
          {isOwner ? (
            <form onSubmit={handleInvite} style={{ display: "flex", gap: "var(--sp-2)" }}>
              <input
                className="input"
                style={{ flex: 1 }}
                type="email"
                placeholder="email@ejemplo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <button className="btn btn-primary" type="submit" disabled={inviting}>
                <Icon name={inviting ? "loader" : "plus"} className={inviting ? "spinning" : ""} />
                Invitar
              </button>
            </form>
          ) : (
            <div className="text-muted" style={{ fontSize: 13 }}>
              Solo el dueño del diagrama puede invitar o quitar colaboradores.
            </div>
          )}

          {error && (
            <div style={{ fontSize: 12, color: "var(--danger)" }}>{error}</div>
          )}

          {loading ? (
            <div className="text-muted" style={{ fontSize: 13 }}>Cargando…</div>
          ) : items.length === 0 ? (
            <div className="text-muted" style={{ fontSize: 13 }}>
              Todavía no invitaste a nadie a este diagrama.
            </div>
          ) : (
            <div style={{ display: "grid", gap: "var(--sp-2)" }}>
              {items.map((c) => (
                <div
                  key={c.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--sp-2)",
                    padding: "var(--sp-2) var(--sp-3)",
                    borderRadius: "var(--radius)",
                    background: "var(--surface-2)",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{c.name}</div>
                    <div className="text-subtle" style={{ fontSize: 11 }}>{c.email}</div>
                  </div>
                  <span className="text-muted" style={{ fontSize: 11 }}>{c.role}</span>
                  {isOwner && (
                    <button
                      className="btn btn-ghost btn-icon"
                      onClick={() => handleRemove(c.user_id)}
                      title="Quitar colaborador"
                    >
                      <Icon name="trash" size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
