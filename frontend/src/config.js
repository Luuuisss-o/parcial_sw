const configuredApiUrl = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const websocketUrl = new URL(configuredApiUrl || window.location.origin, window.location.origin);
websocketUrl.protocol = websocketUrl.protocol === "https:" ? "wss:" : "ws:";

// In Docker the browser uses the frontend origin and Nginx proxies /api to the backend.
export const API_URL = configuredApiUrl;
export const WS_URL = websocketUrl.toString().replace(/\/$/, "");
