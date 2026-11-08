// src/hooks/useTheme.js
import { useEffect, useState } from "react";

// 🔹 Función auxiliar que obtiene el tema inicial
function getInitialTheme() {
  // 1. Revisa si el usuario ya guardó un tema en localStorage
  const saved = localStorage.getItem("theme");
  if (saved === "light" || saved === "dark") return saved;

  // 2. Si no hay guardado, detecta la preferencia del sistema (oscuro/claro)
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;

  // 3. Devuelve "dark" si el sistema prefiere oscuro, caso contrario "light"
  return prefersDark ? "dark" : "light";
}

// 🔹 Hook personalizado para manejar el tema
export default function useTheme() {
  // Estado del tema actual ("light" o "dark"), inicia con lo que devuelva getInitialTheme()
  const [theme, setTheme] = useState(getInitialTheme);

  // 🔹 Efecto: se ejecuta cada vez que cambia `theme`
  useEffect(() => {
    // El sistema de diseño define el tema oscuro en :root y el claro bajo
    // [data-theme="light"], asi que alcanza con setear el atributo.
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  // 🔹 Función para alternar entre "light" y "dark"
  const toggleTheme = () => setTheme(t => (t === "dark" ? "light" : "dark"));

  // 🔹 Retorna el tema actual y la función para cambiarlo
  return { theme, toggleTheme };
}
