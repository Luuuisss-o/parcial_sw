// src/pages/Login.jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import useAuth from "../store/auth";
import ApiStatusBadge from "../components/common/ApiStatusBadge";
import Icon from "../components/common/Icon";
import useTheme from "../hooks/useTheme";
import "./Login.css";

export default function LoginPage() {
  const nav = useNavigate();
  const { token, login } = useAuth();
  const { theme, toggleTheme } = useTheme();

  // "login" o "signup" (crear una cuenta nueva)
  const [mode, setMode] = useState("login");
  const isSignup = mode === "signup";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (token) nav("/", { replace: true });
  }, [token, nav]);

  function switchMode(next) {
    setMode(next);
    setError("");
    setPassword("");
    setPassword2("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");

    if (isSignup) {
      if (password.length < 8) {
        setError("La contraseña tiene que tener al menos 8 caracteres.");
        return;
      }
      if (password !== password2) {
        setError("Las contraseñas no coinciden.");
        return;
      }
    }
    setLoading(true);

    try {
      // Registrarse deja la sesión iniciada: el backend devuelve el token.
      const { data } = isSignup
        ? await api.post("/auth/sign-up", { name, email, password })
        : await api.post("/auth/sign-in", { email, password });
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
        setError(isSignup ? "No se pudo crear la cuenta" : "Email o contraseña incorrectos");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login">
      {/* Panel de marca */}
      <aside className="login-brand">
        <div className="login-logo">
          <span className="login-logo-mark">
            <Icon name="class" size={20} />
          </span>
          UML Collab Tool
        </div>

        <div className="login-hero">
          <h1>
            Diseñá diagramas <em>en equipo</em>, en tiempo real.
          </h1>
          <p>
            Editor colaborativo de diagramas de clases con un asesor de IA que
            revisa tu modelo y propone mejoras.
          </p>
          <ul className="login-features">
            <li><Icon name="users" size={14} /> Colaboración en vivo</li>
            <li><Icon name="sparkles" size={14} /> Asesor de IA</li>
            <li><Icon name="download" size={14} /> Exportá a XMI y código</li>
          </ul>
        </div>

        <svg className="login-art" viewBox="0 0 460 250" aria-hidden="true">
          <path className="uml-link" d="M150 70 H 300" />
          <path className="uml-link" d="M90 112 V 160 Q 90 185 115 185 H 300" />
          <text className="uml-mult" x="158" y="62">1</text>
          <text className="uml-mult" x="282" y="62">*</text>
          <text className="uml-mult" x="264" y="178">0..1</text>

          <g className="uml-float-a">
            <rect className="uml-box" x="30" y="30" width="120" height="82" rx="8" />
            <path className="uml-head-amber" d="M38 30 h104 a8 8 0 0 1 8 8 v18 h-120 v-18 a8 8 0 0 1 8 -8z" />
            <text className="uml-title" x="44" y="48">Cliente</text>
            <rect className="uml-line" x="42" y="68" width="78" height="6" rx="3" />
            <rect className="uml-line" x="42" y="82" width="58" height="6" rx="3" />
            <rect className="uml-line" x="42" y="96" width="68" height="6" rx="3" />
          </g>

          <g className="uml-float-b">
            <rect className="uml-box" x="300" y="22" width="130" height="96" rx="8" />
            <path className="uml-head-mint" d="M308 22 h114 a8 8 0 0 1 8 8 v18 h-130 v-18 a8 8 0 0 1 8 -8z" />
            <text className="uml-title" x="314" y="40">Pedido</text>
            <rect className="uml-line" x="312" y="60" width="90" height="6" rx="3" />
            <rect className="uml-line" x="312" y="74" width="64" height="6" rx="3" />
            <rect className="uml-line" x="312" y="88" width="80" height="6" rx="3" />
            <rect className="uml-line" x="312" y="102" width="50" height="6" rx="3" />
          </g>

          <g className="uml-float-c">
            <rect className="uml-box" x="300" y="150" width="130" height="70" rx="8" />
            <path className="uml-head-coral" d="M308 150 h114 a8 8 0 0 1 8 8 v18 h-130 v-18 a8 8 0 0 1 8 -8z" />
            <text className="uml-title" x="314" y="168">Factura</text>
            <rect className="uml-line" x="312" y="188" width="84" height="6" rx="3" />
            <rect className="uml-line" x="312" y="202" width="60" height="6" rx="3" />
          </g>

          <g className="uml-cursor">
            <path d="M232 104 l0 22 l6 -6 l5 11 l4 -2 l-5 -11 l8 0 z" fill="#f4a940" stroke="#1d1405" strokeWidth="1.2" />
            <rect x="246" y="128" width="46" height="16" rx="8" fill="#f4a940" />
            <text x="253" y="140" fill="#1d1405" style={{ font: "700 10px var(--font)" }}>Diego</text>
          </g>
        </svg>

        <div className="login-brand-foot">Web · Android · IA propia del equipo</div>
      </aside>

      {/* Formulario */}
      <main className="login-main">
        <button
          type="button"
          className="btn btn-ghost btn-icon login-theme"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
          title={theme === "dark" ? "Tema claro" : "Tema oscuro"}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
        </button>
        <div className="login-form-wrap">
          <div className="login-form-head">
            <h2>{isSignup ? "Creá tu cuenta" : "¡Hola de nuevo!"}</h2>
            <p>
              {isSignup
                ? "Registrate para diseñar diagramas con tu equipo."
                : "Iniciá sesión para seguir con tus diagramas."}
            </p>
          </div>

          <form onSubmit={onSubmit} className="login-card">
            <div className="login-tabs" role="tablist" aria-label="Iniciar sesión o crear una cuenta">
              <button
                type="button"
                role="tab"
                aria-selected={!isSignup}
                className={!isSignup ? "active" : ""}
                onClick={() => switchMode("login")}
              >
                Iniciar sesión
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={isSignup}
                className={isSignup ? "active" : ""}
                onClick={() => switchMode("signup")}
              >
                Crear cuenta
              </button>
            </div>

            {isSignup && (
              <div className="field">
                <label className="label" htmlFor="name">Nombre</label>
                <div className="login-input-icon">
                  <Icon name="user" size={16} />
                  <input
                    id="name"
                    className="input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    minLength={2}
                    maxLength={120}
                    autoComplete="name"
                    placeholder="Tu nombre y apellido"
                  />
                </div>
              </div>
            )}

            <div className="field">
              <label className="label" htmlFor="email">Correo electrónico</label>
              <div className="login-input-icon">
                <Icon name="send" size={16} />
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
            </div>

            <div className="field">
              <label className="label" htmlFor="password">Contraseña</label>
              <div className="login-input-icon">
                <Icon name="lock" size={16} />
                <input
                  id="password"
                  className="input"
                  style={{ paddingRight: 44 }}
                  type={showPwd ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete={isSignup ? "new-password" : "current-password"}
                  placeholder={isSignup ? "Al menos 8 caracteres" : "••••••••"}
                />
                <button
                  type="button"
                  className="login-eye"
                  onClick={() => setShowPwd((v) => !v)}
                  aria-label={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
                  title={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
                >
                  <Icon name={showPwd ? "eyeOff" : "eye"} size={16} />
                </button>
              </div>
            </div>

            {isSignup && (
              <div className="field">
                <label className="label" htmlFor="password2">Repetí la contraseña</label>
                <div className="login-input-icon">
                  <Icon name="lock" size={16} />
                  <input
                    id="password2"
                    className="input"
                    type={showPwd ? "text" : "password"}
                    value={password2}
                    onChange={(e) => setPassword2(e.target.value)}
                    required
                    autoComplete="new-password"
                    placeholder="••••••••"
                  />
                </div>
              </div>
            )}

            {error && (
              <div className="login-error" role="alert">
                <Icon name="warning" size={15} />
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-primary login-submit" disabled={loading}>
              {loading && <Icon name="loader" className="spinning" />}
              {loading ? (isSignup ? "Creando la cuenta…" : "Entrando…") : isSignup ? "Crear cuenta" : "Entrar"}
              {!loading && <Icon name="chevronRight" size={16} />}
            </button>
          </form>

          <p className="login-switch">
            {isSignup ? "¿Ya tenés una cuenta? " : "¿No tenés una cuenta? "}
            <button type="button" onClick={() => switchMode(isSignup ? "login" : "signup")}>
              {isSignup ? "Iniciá sesión" : "Creá una"}
            </button>
          </p>

          <div className="login-status">
            <ApiStatusBadge />
          </div>
        </div>
      </main>
    </div>
  );
}
