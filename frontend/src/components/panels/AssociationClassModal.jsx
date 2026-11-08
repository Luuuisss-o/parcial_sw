// src/components/panels/AssociationClassModal.jsx
//
// UML 2.5: una asociación muchos-a-muchos con atributos propios se modela
// como una clase de asociación explícita, no solo como una tabla intermedia
// invisible que Hibernate genera solo por detrás. Este modal aparece apenas
// una relación queda en * en ambos lados, ofreciendo crear esa clase
// intermedia visible en el diagrama.

import Icon from "../common/Icon";

export default function AssociationClassModal({ origenNombre, destinoNombre, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div className="modal-header">
          <h2 className="modal-title">Convertir en clase de asociación</h2>
          <button className="btn btn-ghost btn-icon" onClick={onCancel} title="Cerrar">
            <Icon name="close" />
          </button>
        </div>

        <div className="modal-body" style={{ display: "grid", gap: "var(--sp-3)" }}>
          <div style={{ fontSize: 13 }}>
            <strong>{origenNombre} ↔ {destinoNombre}</strong> ahora es muchos a muchos.
          </div>
          <div className="text-muted" style={{ fontSize: 13 }}>
            Según UML 2.5, esto se puede modelar con una clase de asociación:
            una clase nueva, visible en el diagrama, conectada a ambas con
            multiplicidad 1, con sus propias claves foráneas. Sirve cuando la
            relación en sí necesita tener atributos propios (por ejemplo,
            una fecha o un monto que no pertenecen a ninguna de las dos
            clases originales).
          </div>
          <div className="text-subtle" style={{ fontSize: 12 }}>
            Si preferís no crearla, la relación queda como muchos a muchos
            simple: al exportar el backend igual se genera la tabla
            intermedia, pero no vas a poder agregarle atributos propios acá.
          </div>
        </div>

        <div style={{ display: "flex", gap: "var(--sp-2)", justifyContent: "flex-end", padding: "var(--sp-4)" }}>
          <button className="btn" onClick={onCancel}>
            Dejarla como está
          </button>
          <button className="btn btn-primary" onClick={onConfirm}>
            <Icon name="class" size={14} />
            Crear clase de asociación
          </button>
        </div>
      </div>
    </div>
  );
}
