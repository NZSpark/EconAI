/**
 * Integration Test Helper
 * 
 * Provides auth setup/teardown and shared utilities for integrated tests
 * that hit the real backend API.
 */
import axios from 'axios';

// Configuration — override via environment variables
const API_BASE = process.env.TEST_API_BASE_URL || 'http://localhost:8000';
const TEST_ADMIN = process.env.TEST_ADMIN_USERNAME || 'admin';
const TEST_ADMIN_PASS = process.env.TEST_ADMIN_PASSWORD || 'Admin@123456';

let adminAccessToken: string | null = null;
let adminRefreshToken: string | null = null;
const createdResources: { type: string; id: string; deleteFn?: () => Promise<void> }[] = [];

/**
 * Create an axios instance pointing at the real API.
 */
export function apiClient() {
  const client = axios.create({
    baseURL: `${API_BASE}/api`,
    timeout: 30000,
    validateStatus: () => true, // don't throw on non-2xx
  });

  // Attach auth if available
  client.interceptors.request.use((config) => {
    if (adminAccessToken) {
      config.headers.Authorization = `Bearer ${adminAccessToken}`;
    }
    return config;
  });

  return client;
}

/**
 * Login as admin and store tokens for subsequent requests.
 */
export async function loginAsAdmin(): Promise<void> {
  const client = axios.create({ baseURL: `${API_BASE}/api`, timeout: 15000 });
  try {
    const res = await client.post('/auth/login', {
      username: TEST_ADMIN,
      password: TEST_ADMIN_PASS,
      provider: 'local',
    });
    if (res.status !== 200) {
      throw new Error(`Admin login failed: ${res.status} ${JSON.stringify(res.data)}`);
    }
    adminAccessToken = res.data.access_token;
    adminRefreshToken = res.data.refresh_token;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Cannot connect to backend at ${API_BASE}. Is the server running?\n${msg}`);
  }
}

export function getAccessToken(): string | null {
  return adminAccessToken;
}

/**
 * Register a resource to be cleaned up after test suite completes.
 */
export function trackResource(type: string, id: string, deleteFn?: () => Promise<void>) {
  createdResources.push({ type, id, deleteFn });
}

/**
 * Clean up all tracked resources. Call in afterAll.
 */
export async function cleanupResources(): Promise<void> {
  const client = apiClient();
  // Delete in reverse order (children before parents)
  for (const resource of [...createdResources].reverse()) {
    try {
      if (resource.deleteFn) {
        await resource.deleteFn();
      }
    } catch {
      // best-effort cleanup
    }
  }
  createdResources.length = 0;
}

/**
 * Check if backend is reachable. Call once at suite start.
 */
export async function isBackendAvailable(): Promise<boolean> {
  try {
    const res = await axios.get(`${API_BASE}/health`, { timeout: 5000 });
    return res.status >= 200 && res.status < 400;
  } catch {
    return false;
  }
}
