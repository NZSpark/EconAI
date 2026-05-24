/**
 * Integrated Auth API Tests
 *
 * Tests the real authentication API endpoints against a running backend.
 * Requires: docker-compose up (api-gateway + user-service + postgres + redis)
 *
 * Run with: npm run test:integrated
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import axios from 'axios';
import {
  apiClient,
  loginAsAdmin,
  getAccessToken,
  isBackendAvailable,
} from './test-helper';

const BASE = process.env.TEST_API_BASE_URL || 'http://localhost:8000';

describe('Auth API (Integrated)', () => {
  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) {
      console.warn('⚠ Backend not available — skipping integrated auth tests');
      return;
    }
    await loginAsAdmin();
  });

  it('should login with valid credentials', async () => {
    const client = axios.create({ baseURL: `${BASE}/api`, timeout: 15000, validateStatus: () => true });
    const res = await client.post('/auth/login', {
      username: 'admin',
      password: 'Admin@123456',
      provider: 'local',
    });

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('access_token');
    expect(res.data).toHaveProperty('refresh_token');
    expect(res.data).toHaveProperty('user');
    expect(res.data.user).toHaveProperty('user_id');
    expect(res.data.user).toHaveProperty('username');
    expect(res.data.user).toHaveProperty('role');
  });

  it('should return user info via /auth/me', async () => {
    const token = getAccessToken();
    if (!token) return; // skip if backend unavailable

    const client = apiClient();
    const res = await client.get('/auth/me');

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('user_id');
    expect(res.data).toHaveProperty('username');
    expect(res.data).toHaveProperty('role');
  });

  it('should reject login with invalid credentials', async () => {
    const client = axios.create({ baseURL: `${BASE}/api`, timeout: 15000, validateStatus: () => true });
    const res = await client.post('/auth/login', {
      username: 'nonexistent_user_xyz',
      password: 'wrong_password',
      provider: 'local',
    });

    expect(res.status).toBe(401);
  });

  it('should reject unauthenticated access to /auth/me', async () => {
    const client = axios.create({ baseURL: `${BASE}/api`, timeout: 15000, validateStatus: () => true });
    const res = await client.get('/auth/me');

    expect(res.status).toBe(401);
  });
});
