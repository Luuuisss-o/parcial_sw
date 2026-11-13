// src/components/panels/CollaboratorsModal.jsx
//
// Gestión de colaboradores de un diagrama: solo el dueño puede invitar o
// sacar gente (el backend lo hace cumplir con un 404 si no sos el owner).
// Un colaborador invitado puede abrir el diagrama y editarlo en tiempo real
// junto con el resto -- es lo que hace que la herramienta sea colaborativa
// entre usuarios reales, no solo entre pestañas de la misma persona.
//
// Cada colaborador es "Editor" o "Solo lectura" (ve el diagrama y el chat
// pero no modifica nada). El rol se elige al invitar y se puede cambiar
// después; el cambio le llega en vivo a quien tenga el diagrama abierto.

import { useEffect, useState } from "react";
import Icon from "../common/Icon";
import { listCollaborators, addCollaborator, removeCollaborator } from "../../api/diagrams";

const ROLES = [
  { v: "EDITOR", label: "Editor", ayuda: "Puede modificar el diagrama." },
  { v: "VIEWER", label: "Solo lectura", ayuda: "Ve el diagrama y el chat, pero no modifica nada." },
];

export default function CollaboratorsModal({ diagram, isOwner, onClose }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("EDITOR");
  const [inviting, setInviting] = useState(false);
  const [changing, setChanging] = useState(null); // user_id cuyo rol se está guardando
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
      await addCollaborator(diagram.id, email.trim(), role);
      setEmail("");
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "No se pudo invitar a ese usuario");
    } finally {
      setInviting(false);
    }
  };

  // Cambiar el rol de alguien ya invitado: el backend actualiza el rol si se
  // vuelve a invitar al mismo correo.
  const handleRole = async (c, newRole) => {
    setChanging(c.user_id);
    setError(null);
    try {
      const updated = await addCollaborator(diagram.id, c.email, newRole);
      setItems((prev) => prev.map((x) => (x.user_id === c.user_id ? { ...x, role: updated.role } : x)));
    } catch (err) {
      setError(err?.response?.data?.detail || "No se pudo cambiar el rol");
    } finally {
      setChanging(null);
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
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div className="modal-header">
          <h2 className="modal-title">Colaboradores</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose} title="Cerrar">
            <Icon name="close" />
          </button>
        </div>

        <div className="modal-body scroll" style={{ display: "grid", gap: "var(--sp-3)" }}>
          {isOwner ? (
            <form onSubmit={handleInvite} style={{ display: "grid", gap: "var(--sp-2)" }}>
              <div style={{ display: "flex", gap: "var(--sp-2)" }}>
                <input
                  className="input"
                  style={{ flex: 1 }}
                  type="email"
                  placeholder="email@ejemplo.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
                <select
                  className="select"
                  style={{ width: 140 }}
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  aria-label="Permiso del colaborador"
                  data-testid="invite-role"
                >
                  {ROLES.map((r) => (
                    <option key={r.v} value={r.v}>{r.label}</option>
                  ))}
                </select>
                <button className="btn btn-primary" type="submit" disabled={inviting}>
                  <Icon name={inviting ? "loader" : "plus"} className={inviting ? "spinning" : ""} />
                  Invitar
                </button>
              </div>
              <div className="text-subtle" style={{ fontSize: 12 }}>
                {ROLES.find((r) => r.v === role)?.ayuda}
              </div>
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
                  {isOwner ? (
                    <select
                      className="select input-sm"
                      style={{ width: 130 }}
                      value={c.role}
                      disabled={changing === c.user_id}
                      onChange={(e) => handleRole(c, e.target.value)}
                      aria-label={`Permiso de ${c.name}`}
                    >
                      {ROLES.map((r) => (
                        <option key={r.v} value={r.v}>{r.label}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-muted" style={{ fontSize: 11 }}>
                      {ROLES.find((r) => r.v === c.role)?.label ?? c.role}
                    </span>
                  )}
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
