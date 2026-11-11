// src/pages/Home.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import useAuth from "../store/auth";
import useTheme from "../hooks/useTheme";
import ApiStatusBadge from "../components/common/ApiStatusBadge";
import Icon from "../components/common/Icon";
import ImportFromPhotoModal from "../components/panels/ImportFromPhotoModal";
import "./Home.css";

// Color de la franja de cada tarjeta (ámbar, menta, coral), como en la app móvil.
const STRIPS = ["#f4a940", "#3fc7a8", "#ef7a5a"];

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
    <div className="home">
      {/* ---------- Barra superior (marca) ---------- */}
      <header className="brand-bar home-bar">
        <span className="brand-logo" aria-hidden="true">
          <Icon name="class" size={16} />
        </span>
        <strong>UML Collab Tool</strong>
        <ApiStatusBadge />

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <button
            className="btn btn-ghost btn-icon"
            onClick={toggleTheme}
            title={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
          <div className="brand-sep" />
          <span className="text-muted home-email" style={{ fontSize: 12 }}>{email}</span>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => { logout(); nav("/login", { replace: true }); }}
            title="Cerrar sesión"
          >
            <Icon name="logout" />
          </button>
        </div>
      </header>

      <main className="scroll">
        {/* ---------- Franja de bienvenida ---------- */}
        <section className="brand-bar home-hero">
          <div className="home-hero-inner">
            <h1>
              Mis <em>diagramas</em>
            </h1>
            <p className="text-muted">
              Cada diagrama es un modelo de clases UML del que después podés generar un backend
              Spring Boot completo. Trabajalo en equipo, en tiempo real, con el asesor de IA.
            </p>
            <div className="home-chips">
              <span>
                <Icon name="file" size={13} />
                {total} diagrama{total === 1 ? "" : "s"}
              </span>
              <span>
                <Icon name="users" size={13} /> Colaboración en vivo
              </span>
              <span>
                <Icon name="camera" size={13} /> Importá desde una foto
              </span>
            </div>
          </div>
        </section>

        <div className="home-content">
          {/* Crear */}
          <form onSubmit={createDiagram} className="home-create">
            <label className="label" htmlFor="nuevo-diagrama" style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
              Crear un diagrama nuevo
            </label>
            <div className="home-create-row">
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
              <button
                type="button"
                className="btn"
                onClick={() => setShowImport(true)}
                title="Crear un diagrama a partir de una foto: de clases o de base de datos"
              >
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
          <h2 className="home-section-title">Tus diagramas</h2>
          {loading ? (
            <div className="text-muted" style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center", fontSize: 13 }}>
              <Icon name="loader" className="spinning" />
              Cargando…
            </div>
          ) : diagrams.length === 0 ? (
            <div className="home-empty">
              <div className="home-empty-icon">
                <Icon name="class" size={24} />
              </div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>Todavía no tenés diagramas</div>
              <div className="text-muted" style={{ fontSize: 13, maxWidth: 400 }}>
                Creá el primero con el formulario de arriba o importalo desde una foto. Al abrirlo vas
                a encontrar una guía paso a paso para empezar.
              </div>
            </div>
          ) : (
            <div className="home-list">
              {diagrams.map((d, i) => (
                <div
                  key={d.id}
                  className="home-card"
                  style={{ "--strip": STRIPS[i % STRIPS.length] }}
                  onClick={() => nav(`/diagram/${d.id}`)}
                >
                  <div className="home-card-icon">
                    <Icon name="class" size={19} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="home-card-title">{d.title}</div>
                    {d.updated_at && (
                      <span className="home-card-date">
                        Modificado {new Date(d.updated_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={(e) => { e.stopPropagation(); nav(`/diagram/${d.id}`); }}
                  >
                    Abrir
                  </button>
                  <button
                    className="btn btn-danger-ghost btn-icon btn-sm"
                    onClick={(e) => { e.stopPropagation(); removeDiagram(d.id, d.title); }}
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
