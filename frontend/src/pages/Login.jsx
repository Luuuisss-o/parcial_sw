// src/pages/Login.jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import useAuth from "../store/auth";
import ApiStatusBadge from "../components/common/ApiStatusBadge";
import Icon from "../components/common/Icon";

export default function LoginPage() {
  const nav = useNavigate();
  const { token, login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (token) nav("/", { replace: true });
  }, [token, nav]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const { data } = await api.post("/auth/sign-in", { email, password });
      login(data.access_token);
      nav("/", { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;

      if (Array.isArray(detail)) {
        setError(detail[0]?.msg || "Revisá los datos ingresados");
      } else if (typeof detail === "string") {
        setError(detail);
      } else if (typeof detail === "object" && detail?.msg) {
        setError(detail.msg);
      } else if (err?.code === "ERR_NETWORK") {
        setError("No se pudo conectar con el servidor. ¿Está encendido el backend?");
      } else {
        setError("Email o contraseña incorrectos");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "var(--bg)",
        color: "var(--text)",
        padding: "var(--sp-4)",
      }}
    >
      <div style={{ width: "100%", maxWidth: 380, display: "grid", gap: "var(--sp-4)" }}>
        {/* Marca */}
        <div style={{ display: "grid", gap: "var(--sp-2)", justifyItems: "center", textAlign: "center" }}>
          <div
            style={{
              width: 46,
              height: 46,
              display: "grid",
              placeItems: "center",
              borderRadius: "var(--radius-lg)",
              background: "var(--accent-soft)",
              color: "var(--accent)",
            }}
          >
            <Icon name="class" size={22} />
          </div>
          <h1 style={{ margin: 0, fontSize: 19, fontWeight: 650 }}>UML Collab Tool</h1>
          <p className="text-muted" style={{ margin: 0, fontSize: 13 }}>
            Editor colaborativo de diagramas de clases
          </p>
        </div>

        <form onSubmit={onSubmit} className="card" style={{ display: "grid", gap: "var(--sp-4)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            <strong style={{ fontSize: 14, flex: 1 }}>Iniciar sesión</strong>
            <ApiStatusBadge />
          </div>

          <div className="field">
            <label className="label" htmlFor="email">Correo electrónico</label>
            <input
              id="email"
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
              placeholder="usuario@ejemplo.com"
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="password">Contraseña</label>
            <div style={{ position: "relative" }}>
              <input
                id="password"
                className="input"
                style={{ paddingRight: 40 }}
                type={showPwd ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPwd((v) => !v)}
                style={{
                  position: "absolute",
                  right: 6,
                  top: "50%",
                  transform: "translateY(-50%)",
                  display: "grid",
                  placeItems: "center",
                  width: 26,
                  height: 26,
                  border: "none",
                  background: "transparent",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  padding: 0,
                }}
                aria-label={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
                title={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
              >
                <Icon name={showPwd ? "eyeOff" : "eye"} size={15} />
              </button>
            </div>
          </div>

          {error && (
            <div
              style={{
                display: "flex",
                gap: "var(--sp-2)",
                alignItems: "center",
                padding: "var(--sp-2) var(--sp-3)",
                borderRadius: "var(--radius)",
                background: "var(--danger-soft)",
                color: "var(--danger)",
                fontSize: 12,
              }}
            >
              <Icon name="warning" size={14} />
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={loading} style={{ height: 38 }}>
            {loading && <Icon name="loader" className="spinning" />}
            {loading ? "Entrando…" : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
