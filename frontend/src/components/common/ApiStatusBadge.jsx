import { useEffect, useState } from "react";
import api from "../../api/client";

export default function ApiStatusBadge() {
  const [ok, setOk] = useState(null);

  useEffect(() => {
    let mounted = true;
    api
      .get("/health")
      .then(() => mounted && setOk(true))
      .catch(() => mounted && setOk(false));
    return () => {
      mounted = false;
    };
  }, []);

  const clase = ok === null ? "badge-muted" : ok ? "badge-success" : "badge-danger";
  const texto = ok === null ? "Conectando…" : ok ? "Servidor conectado" : "Servidor sin conexión";

  return (
    <span className={`badge ${clase}`} title="Estado de la conexión con el servidor">
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "currentColor",
          display: "inline-block",
        }}
      />
      {texto}
    </span>
  );
}
