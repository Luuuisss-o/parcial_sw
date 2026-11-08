// src/components/common/HelpGuide.jsx
//
// Guía de uso de la herramienta. Se abre desde el botón de ayuda de la barra
// superior y, la primera vez que alguien entra a un diagrama, sola.

import { useState } from "react";
import Icon from "./Icon";

const PASOS = [
  {
    icon: "class",
    titulo: "1. Creá una clase",
    detalle:
      "Hacé clic en «Nueva clase» arriba y después en cualquier punto del lienzo. Ahí se coloca la clase. Es el equivalente a una tabla de tu base de datos.",
  },
  {
    icon: "attribute",
    titulo: "2. Agregale atributos",
    detalle:
      "Seleccioná una clase y usá el panel «Inspector» de la derecha para agregar atributos (nombre y tipo). Cada atributo será una columna en la base de datos generada.",
  },
  {
    icon: "relation",
    titulo: "3. Conectá las clases",
    detalle:
      "Pasá el mouse por el borde de una clase: aparecen puntos de conexión. Arrastrá desde uno hasta otra clase para crear la relación, y elegí su tipo y multiplicidad en el panel derecho.",
  },
  {
    icon: "sparkles",
    titulo: "4. Conversá con tu equipo y con la IA",
    detalle:
      "Abrí el «Chat del equipo» abajo a la derecha para hablar con los demás colaboradores en tiempo real. Para pedirle algo al asistente empezá el mensaje con «@IA» (o tocá el botón ✨): «@IA creá una clase Cliente con nombre y email». También podés hacerle preguntas teóricas («@IA ¿qué es un requerimiento delegado?»): responde como mentor de diseño sin tocar el diagrama. Todo el equipo ve la pregunta y la respuesta, y la IA te responde a vos por tu nombre.",
  },
  {
    icon: "download",
    titulo: "5. Generá el backend",
    detalle:
      "Cuando el diagrama esté listo, usá «Exportar backend». Se descarga un proyecto Spring Boot completo (entidades, repositorios, servicios y controladores) listo para abrir en tu IDE.",
  },
];

const CONCEPTOS = [
  ["Clase", "Una entidad del sistema. Se convierte en una tabla."],
  ["Atributo", "Un dato de esa entidad. Se convierte en una columna."],
  ["Método", "Una operación de la clase. Es opcional para la base de datos."],
  ["Asociación", "Dos clases se relacionan, pero existen por separado."],
  ["Agregación", "Una contiene a la otra, pero la otra sobrevive sin ella."],
  ["Composición", "Una contiene a la otra y sin la primera la otra no existe."],
  ["Herencia", "Una clase es un tipo especializado de otra."],
  ["Multiplicidad", "Cuántos elementos participan: 1, 0..1, 1..* o *."],
];

export default function HelpGuide({ onClose }) {
  const [tab, setTab] = useState("pasos");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Cómo usar esta herramienta</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose} title="Cerrar">
            <Icon name="close" />
          </button>
        </div>

        <div style={{ display: "flex", gap: "var(--sp-1)", padding: "0 var(--sp-4)", borderBottom: "1px solid var(--border)" }}>
          {[
            ["pasos", "Primeros pasos"],
            ["conceptos", "Glosario UML"],
          ].map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              style={{
                padding: "var(--sp-3) var(--sp-3)",
                border: "none",
                borderBottom: `2px solid ${tab === id ? "var(--accent)" : "transparent"}`,
                background: "transparent",
                color: tab === id ? "var(--text)" : "var(--text-muted)",
                font: "inherit",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="modal-body scroll">
          {tab === "pasos" ? (
            <div style={{ display: "grid", gap: "var(--sp-4)" }}>
              {PASOS.map((p) => (
                <div key={p.titulo} style={{ display: "flex", gap: "var(--sp-3)" }}>
                  <div
                    style={{
                      width: 34,
                      height: 34,
                      flexShrink: 0,
                      display: "grid",
                      placeItems: "center",
                      borderRadius: "var(--radius)",
                      background: "var(--accent-soft)",
                      color: "var(--accent)",
                    }}
                  >
                    <Icon name={p.icon} size={17} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{p.titulo}</div>
                    <div className="text-muted" style={{ fontSize: 13 }}>
                      {p.detalle}
                    </div>
                  </div>
                </div>
              ))}

              <div
                style={{
                  display: "flex",
                  gap: "var(--sp-2)",
                  padding: "var(--sp-3)",
                  borderRadius: "var(--radius)",
                  background: "var(--surface-2)",
                }}
              >
                <Icon name="info" size={15} style={{ color: "var(--accent)", marginTop: 2 }} />
                <div className="text-muted" style={{ fontSize: 12 }}>
                  El diagrama es <strong>colaborativo</strong>: si otra persona lo abre al mismo
                  tiempo, los cambios de cada uno aparecen en la pantalla del otro al instante,
                  sin recargar la página.
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "var(--sp-2)",
                  padding: "var(--sp-3)",
                  borderRadius: "var(--radius)",
                  background: "var(--surface-2)",
                }}
              >
                <Icon name="check" size={15} style={{ color: "var(--success)", marginTop: 2 }} />
                <div className="text-muted" style={{ fontSize: 12 }}>
                  <strong>No hay botón de guardar</strong>: todo se guarda solo mientras
                  trabajás. Si te equivocás, usá <strong>Ctrl+Z</strong> (o el botón de deshacer
                  de la barra) para revertir el último cambio.
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gap: "var(--sp-3)" }}>
              {CONCEPTOS.map(([termino, definicion]) => (
                <div key={termino} style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "var(--sp-3)" }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{termino}</div>
                  <div className="text-muted" style={{ fontSize: 13 }}>
                    {definicion}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ padding: "var(--sp-3) var(--sp-4)", borderTop: "1px solid var(--border)", textAlign: "right" }}>
          <button className="btn btn-primary" onClick={onClose}>
            Entendido
          </button>
        </div>
      </div>
    </div>
  );
}
