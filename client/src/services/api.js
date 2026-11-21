import axios from "axios";

// Base URL of the Siora One API, including the /api/ prefix.
// Set VITE_API_URL at build time (e.g. https://siora-one-api.vercel.app/api/);
// falls back to the local Django dev server.
export const API_BASE_URL = (
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api/"
).replace(/\/?$/, "/");

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

if (import.meta.env.DEV) console.log("API Base URL:", api.defaults.baseURL);

let isRefreshing = false;
let refreshPromise = null;

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Handle network errors (no internet connection)
    if (!error.response) {
      // Network error - no response received
      error.message = "please check internet connection";
      return Promise.reject(error);
    }

    const isAuthEndpoint =
      originalRequest?.url?.includes("auth/login/") ||
      originalRequest?.url?.includes("auth/refresh/");

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;

      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user_info");
        window.location.href = "/login";
        return Promise.reject(error);
      }

      try {
        // Queue concurrent 401 requests behind a single refresh call.
        // This avoids random logouts when many button clicks trigger parallel API calls.
        if (!isRefreshing) {
          isRefreshing = true;
          refreshPromise = axios.post(`${API_BASE_URL}auth/refresh/`, {
            refresh: refreshToken,
          });
        }

        const response = await refreshPromise;
        const { access } = response.data;

        localStorage.setItem("access_token", access);
        api.defaults.headers.common["Authorization"] = `Bearer ${access}`;
        originalRequest.headers.Authorization = `Bearer ${access}`;

        return api(originalRequest);
      } catch (refreshError) {
        // Logout only when refresh token is actually invalid/expired.
        // For transient failures (network/proxy), keep session data intact.
        const refreshStatus = refreshError.response?.status;
        if (refreshStatus === 401 || refreshStatus === 403) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("user_info");
          window.location.href = "/login";
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
        refreshPromise = null;
      }
    }
    return Promise.reject(error);
  },
);

export default api;
