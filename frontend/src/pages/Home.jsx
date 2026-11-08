// src/pages/Home.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import useAuth from "../store/auth";
import useTheme from "../hooks/useTheme";
import ApiStatusBadge from "../components/common/ApiStatusBadge";
import Icon from "../components/common/Icon";
import ImportFromPhotoModal from "../components/panels/ImportFromPhotoModal";

import {
  listDiagrams as apiListDiagrams,
  createDiagram as apiCreateDiagram,
  deleteDiagram as apiDeleteDiagram,
} from "../api/diagrams";

export default function HomePage() {
  const nav = useNavigate();
  const logout = useAuth((s) => s.logout);
  const email = useAuth((s) => s.email);
  const { theme, toggleTheme } = useTheme();

  const [title, setTitle] = useState("");
  const [diagrams, setDiagrams] = useState([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [creating, setCreating] = useState(false);
  const [showImport, setShowImport] = useState(false);

  async function load() {
    setLoading(true);
    setMsg("");
    try {
      const data = await apiListDiagrams({ page, limit });
      setDiagrams(data?.items ?? []);
      setTotal(data?.total ?? 0);
    } catch (e) {
      setMsg(e?.response?.data?.detail || "No se pudieron cargar los diagramas");
      setDiagrams([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  async function createDiagram(e) {
    e?.preventDefault?.();
    if (!title.trim() || creating) return;
    setMsg("");
    setCreating(true);
    try {
      const d = await apiCreateDiagram(title.trim());
      setTitle("");
      nav(`/diagram/${d.id}`);
    } catch (e) {
      setMsg(e?.response?.data?.detail || "No se pudo crear el diagrama");
    } finally {
      setCreating(false);
    }
  }

  async function removeDiagram(id, nombre) {
    if (!confirm(`¿Eliminar el diagrama "${nombre}"? Esta acción no se puede deshacer.`)) return;
    try {
      await apiDeleteDiagram(id);
      await load();
    } catch (e) {
      alert(e?.response?.data?.detail || "No se pudo eliminar");
    }
  }

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / limit)), [total, limit]);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "var(--header-h) 1fr",
        height: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
      }}
    >
      {/* ---------- Barra superior ---------- */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-3)",
          padding: "0 var(--sp-5)",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface-1)",
        }}
      >
        <Icon name="class" size={18} style={{ color: "var(--accent)" }} />
        <strong style={{ fontSize: 14 }}>UML Collab Tool</strong>
        <ApiStatusBadge />

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <button
            className="btn btn-ghost btn-icon"
            onClick={toggleTheme}
            title={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
          <div style={{ width: 1, height: 22, background: "var(--border)" }} />
          <span className="text-muted" style={{ fontSize: 12 }}>{email}</span>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => { logout(); nav("/login", { replace: true }); }}
            title="Cerrar sesión"
          >
            <Icon name="logout" />
          </button>
        </div>
      </header>

      {/* ---------- Contenido ---------- */}
      <main className="scroll" style={{ padding: "var(--sp-6) var(--sp-5)" }}>
        <div style={{ maxWidth: 780, margin: "0 auto", display: "grid", gap: "var(--sp-5)" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 650 }}>Mis diagramas</h1>
            <p className="text-muted" style={{ margin: "var(--sp-2) 0 0", fontSize: 13 }}>
              Cada diagrama es un modelo de clases UML del que después podés generar
              un backend Spring Boot completo.
            </p>
          </div>

          {/* Crear */}
          <form onSubmit={createDiagram} className="card" style={{ display: "grid", gap: "var(--sp-3)" }}>
            <label className="label" htmlFor="nuevo-diagrama">Crear un diagrama nuevo</label>
            <div style={{ display: "flex", gap: "var(--sp-2)" }}>
              <input
                id="nuevo-diagrama"
                className="input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ej: Sistema de ventas"
              />
              <button type="submit" className="btn btn-primary" disabled={!title.trim() || creating}>
                <Icon name={creating ? "loader" : "plus"} className={creating ? "spinning" : ""} />
                {creating ? "Creando…" : "Crear"}
              </button>
              <button type="button" className="btn" onClick={() => setShowImport(true)} title="Crear un diagrama a partir de una foto del pizarrón">
                <Icon name="camera" />
                Importar desde foto
              </button>
            </div>
            {msg && (
              <div style={{ fontSize: 12, color: "var(--danger)", display: "flex", gap: 6, alignItems: "center" }}>
                <Icon name="warning" size={13} />
                {msg}
              </div>
            )}
          </form>

          {/* Lista */}
          {loading ? (
            <div className="text-muted" style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center", fontSize: 13 }}>
              <Icon name="loader" className="spinning" />
              Cargando…
            </div>
          ) : diagrams.length === 0 ? (
            <div
              className="card"
              style={{ display: "grid", gap: "var(--sp-2)", justifyItems: "center", textAlign: "center", padding: "var(--sp-6)" }}
            >
              <div
                style={{
                  width: 44, height: 44, display: "grid", placeItems: "center",
                  borderRadius: "var(--radius)", background: "var(--surface-2)", color: "var(--text-subtle)",
                }}
              >
                <Icon name="folder" size={20} />
              </div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>Todavía no tenés diagramas</div>
              <div className="text-muted" style={{ fontSize: 13, maxWidth: 380 }}>
                Creá el primero con el formulario de arriba. Al abrirlo vas a encontrar una
                guía paso a paso para empezar.
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gap: "var(--sp-2)" }}>
              {diagrams.map((d) => (
                <div
                  key={d.id}
                  className="card"
                  style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", padding: "var(--sp-3) var(--sp-4)" }}
                >
                  <Icon name="file" size={17} style={{ color: "var(--text-subtle)" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{d.title}</div>
                    {d.updated_at && (
                      <div className="text-subtle" style={{ fontSize: 11 }}>
                        Modificado {new Date(d.updated_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                  <button className="btn btn-primary btn-sm" onClick={() => nav(`/diagram/${d.id}`)}>
                    Abrir
                  </button>
                  <button
                    className="btn btn-danger-ghost btn-icon btn-sm"
                    onClick={() => removeDiagram(d.id, d.title)}
                    title="Eliminar diagrama"
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Paginación */}
          {totalPages > 1 && (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", justifyContent: "center" }}>
              <button className="btn btn-icon btn-sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <Icon name="chevronLeft" size={14} />
              </button>
              <span className="text-muted" style={{ fontSize: 12 }}>
                Página {page} de {totalPages}
              </span>
              <button className="btn btn-icon btn-sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                <Icon name="chevronRight" size={14} />
              </button>
            </div>
          )}
        </div>
      </main>

      {showImport && (
        <ImportFromPhotoModal
          onClose={() => setShowImport(false)}
          onImported={(diagramId) => {
            setShowImport(false);
            nav(`/diagram/${diagramId}`);
          }}
        />
      )}
    </div>
  );
}
