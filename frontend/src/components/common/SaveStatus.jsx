// src/components/common/SaveStatus.jsx
//
// Indicador chico de estado de guardado automático, compartido por los
// paneles de edición (Inspector de clase, RelationInspector) que usan
// useAutoSave: ninguno tiene botón "Guardar", cada campo se persiste solo,
// y esto es lo que le confirma al usuario que el cambio realmente llegó al
// servidor (o que falló, en vez de descartarse en silencio).

import Icon from "./Icon";

export function SaveStatus({ status }) {
  if (status === "saving") {
    return (
      <span className="text-subtle" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11 }}>
        <Icon name="loader" size={11} className="spinning" />
        Guardando
      </span>
    );
  }
  if (status === "saved") {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--success)" }}>
        <Icon name="check" size={11} />
        Guardado
      </span>
    );
  }
  return null;
}

export function RowError({ message }) {
  if (!message) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--danger)" }}>
      <Icon name="warning" size={12} />
      {message}
    </div>
  );
}
