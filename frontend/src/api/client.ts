import axios from 'axios';
import type { ApiError } from './types';

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function generateRequestId(): string {
  const segments = [8, 4, 4, 4, 12];
  return segments
    .map((len) =>
      Array.from({ length: len }, () =>
        Math.floor(Math.random() * 16).toString(16)
      ).join('')
    )
    .join('-');
}

export function isUUID(value: string): boolean {
  return UUID_REGEX.test(value);
}

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  // 不设默认 Content-Type，让 Axios 根据 body 类型自动判断：
  // - 普通对象 → application/json
  // - FormData → multipart/form-data (带 boundary)
});

// Request interceptor: attach auth token and X-Request-ID
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  config.headers['X-Request-ID'] = generateRequestId();
  return config;
});

// Track refresh state to prevent concurrent refresh calls
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else if (token) {
      promise.resolve(token);
    }
  });
  failedQueue = [];
}

// Response interceptor: handle 401 and unified error extraction
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and not already retrying, attempt token refresh
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/refresh')
    ) {
      if (isRefreshing) {
        // Queue the request until refresh completes
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(client(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        isRefreshing = false;
        processQueue(new Error('No refresh token'), null);
        localStorage.removeItem('access_token');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        const response = await axios.post('/api/auth/refresh', {
          refresh_token: refreshToken,
        });
        const { access_token, refresh_token } = response.data;
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', refresh_token);

        processQueue(null, access_token);

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return client(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // Extract unified API error
    const apiError: ApiError | undefined = error.response?.data;
    if (apiError?.error) {
      const enhanced = new Error(apiError.error.message) as Error & {
        code: string;
        status: number;
        details?: Record<string, unknown>;
      };
      enhanced.code = apiError.error.code;
      enhanced.status = error.response.status;
      enhanced.details = apiError.error.details;
      return Promise.reject(enhanced);
    }

    return Promise.reject(error);
  }
);

export default client;