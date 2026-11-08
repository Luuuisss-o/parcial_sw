import axios from "axios";
import useAuth from "../store/auth";
import { API_URL } from "../config";

const api = axios.create({
  baseURL: API_URL,
  timeout: 10000,
});

// ====== INTERCEPTOR DE REQUEST ======
api.interceptors.request.use((config) => {
  const { token } = useAuth.getState();

  console.log("📤 [API Request]", {
    url: config.baseURL + config.url,
    method: config.method,
    headers: config.headers,
    data: config.data,
  });

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ====== INTERCEPTOR DE RESPONSE ======
api.interceptors.response.use(
  (response) => {
    console.log("📥 [API Response]", {
      url: response.config.url,
      status: response.status,
      data: response.data,
    });
    return response;
  },
  (error) => {
    console.error("❌ [API Error]", {
      url: error?.config?.url,
      status: error?.response?.status,
      data: error?.response?.data,
      message: error?.message,
    });

    if (error?.response?.status === 401) {
      try {
        useAuth.getState().logout();
      } catch {}
      window.location.href = "/login";
    }

    return Promise.reject(error);
  }
);

export default api;
