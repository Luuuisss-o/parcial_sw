// src/components/layout/HeaderBar.jsx
import { useRef } from "react";
import Icon from "../common/Icon";

function timeAgo(iso) {
  if (!iso) return null;
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "hace un momento";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return new Date(iso).toLocaleDateString();
}

export default function HeaderBar({
  diagram,
  email,
  theme,
  toggleTheme,
  onBack,
  insertMode,
  setInsertMode,
  onLogout,
  onExport,
  exporting,
  onExportXmi,
  exportingXmi,
  onImportXmiFile,
  importingXmi,
  onOpenHelp,
  onUndo,
  canUndo,
  onOpenCollaborators,
}) {
  const xmiInputRef = useRef(null);

  return (
    <header
      style={{
        height: "var(--header-h)",
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-3)",
        padding: "0 var(--sp-4)",
        borderBottom: "1px solid var(--border)",
        background: "var(--surface-1)",
        position: "relative",
        zIndex: "var(--z-chrome)",
      }}
    >
      <button className="btn btn-ghost btn-icon" onClick={onBack} title="Volver a mis diagramas">
        <Icon name="back" />
      </button>

      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {diagram.title}
        </div>
        <div className="text-subtle" style={{ fontSize: 11 }}>
          Guardado {timeAgo(diagram.updated_at)}
        </div>
      </div>

      <div style={{ marginLeft: "var(--sp-4)", display: "flex", gap: "var(--sp-2)" }}>
        <button
          className={`btn ${insertMode ? "btn-active" : ""}`}
          onClick={() => setInsertMode((v) => !v)}
          title="Agregar una clase nueva al diagrama"
        >
          <Icon name="plus" />
          Nueva clase
        </button>

        <button
          className="btn btn-icon"
          onClick={onUndo}
          disabled={!canUndo}
          title={canUndo ? "Deshacer el último cambio (Ctrl+Z)" : "No hay nada para deshacer"}
        >
          <Icon name="undo" />
        </button>

        <button
          className="btn"
          onClick={onExport}
          disabled={exporting}
          title="Generar el proyecto Spring Boot a partir de este diagrama"
        >
          <Icon name={exporting ? "loader" : "download"} className={exporting ? "spinning" : ""} />
          {exporting ? "Generando…" : "Exportar backend"}
        </button>

        <div style={{ width: 1, height: 22, background: "var(--border)", alignSelf: "center" }} />

        <button
          className="btn btn-icon"
          onClick={onOpenCollaborators}
          title="Gestionar colaboradores de este diagrama"
        >
          <Icon name="users" />
        </button>

        <div style={{ width: 1, height: 22, background: "var(--border)", alignSelf: "center" }} />

        <button
          className="btn btn-icon"
          onClick={onExportXmi}
          disabled={exportingXmi}
          title="Exportar el diagrama como .xmi (interoperable con Enterprise Architect)"
        >
          <Icon name={exportingXmi ? "loader" : "file"} className={exportingXmi ? "spinning" : ""} />
        </button>

        <button
          className="btn btn-icon"
          onClick={() => xmiInputRef.current?.click()}
          disabled={importingXmi}
          title="Importar un diagrama desde un archivo .xmi"
        >
          <Icon name={importingXmi ? "loader" : "upload"} className={importingXmi ? "spinning" : ""} />
        </button>
        <input
          ref={xmiInputRef}
          type="file"
          accept=".xmi,.xml,application/xml,text/xml"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            onImportXmiFile?.(file);
            e.target.value = ""; // permite reimportar el mismo archivo dos veces seguidas
          }}
        />
      </div>

      <div
        style={{
          marginLeft: "auto",
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
        }}
      >
        <button className="btn btn-ghost btn-icon" onClick={onOpenHelp} title="¿Cómo se usa esta herramienta?">
          <Icon name="help" />
        </button>
        <button
          className="btn btn-ghost btn-icon"
          onClick={toggleTheme}
          title={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>

        <div style={{ width: 1, height: 22, background: "var(--border)" }} />

        <span className="text-muted" style={{ fontSize: 12 }}>
          {email}
        </span>
        <button className="btn btn-ghost btn-icon" onClick={onLogout} title="Cerrar sesión">
          <Icon name="logout" />
        </button>
      </div>
    </header>
  );
}
