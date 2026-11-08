import { create } from "zustand";
import { jwtDecode } from "jwt-decode";

const TOKEN_KEY = "uml_access_token";
const EMAIL_KEY = "uml_email";

// Carga inicial desde localStorage
const initialToken = localStorage.getItem(TOKEN_KEY) || "";
let initialUser = null;
try { if (initialToken) initialUser = jwtDecode(initialToken); } catch {}
const initialEmail = localStorage.getItem(EMAIL_KEY) || (initialUser?.sub ?? "");

/** Store de auth (token + payload decodificado) */
const useAuth = create((set, get) => ({
  token: initialToken,
  user: initialUser,     // payload JWT (sub, iat, exp, kind...)
  email: initialEmail,   // sub=email en tu backend

  /** Guarda token, decodifica y persiste email */
  login: (token) => {
    try {
      const payload = jwtDecode(token);
      const email = payload?.sub || "";
      localStorage.setItem(TOKEN_KEY, token);
      if (email) localStorage.setItem(EMAIL_KEY, email);
      else localStorage.removeItem(EMAIL_KEY);
      set({ token, user: payload, email });
    } catch {
      // token inválido
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(EMAIL_KEY);
      set({ token: "", user: null, email: "" });
      throw new Error("Token inválido");
    }
  },

  /** Limpia sesión */
  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
    set({ token: "", user: null, email: "" });
  },
}));

/** Helpers para usar fuera de componentes (p.ej. en axios interceptors) */
export const getToken = () => useAuth.getState().token;
export const getEmail = () => useAuth.getState().email;
export const isAuthenticated = () => !!useAuth.getState().token;

export default useAuth;
