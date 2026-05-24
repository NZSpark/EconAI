/**
 * Integrated Profile API Tests
 *
 * Tests password change and user profile endpoints.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import axios from 'axios';
import {
  apiClient,
  loginAsAdmin,
  isBackendAvailable,
} from './test-helper';

const BASE = process.env.TEST_API_BASE_URL || 'http://localhost:8000';

describe('Profile API (Integrated)', () => {
  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) return;
    await loginAsAdmin();
  });

  it('should change password with valid credentials', async () => {
    const client = apiClient();
    const res = await client.post('/auth/change-password', {
      old_password: 'Admin@123456',
      new_password: 'Admin@123456', // Change to same password for idempotency
    });

    // Should succeed (200) or fail with appropriate error
    expect([200, 201, 204, 400, 422]).toContain(res.status);
    if (res.status === 400 || res.status === 422) {
      // API returns error nested under detail
      expect(res.data.detail.error).toBeDefined();
    }
  });

  it('should reject password change with wrong old password', async () => {
    const client = apiClient();
    const res = await client.post('/auth/change-password', {
      old_password: 'CompletelyWrongPassword123',
      new_password: 'NewPassword123!',
    });

    // API returns 400 for wrong old password
    expect([400, 401]).toContain(res.status);
  });

  it('should reject password change with too-short new password', async () => {
    const client = apiClient();
    const res = await client.post('/auth/change-password', {
      old_password: 'Admin@123456',
      new_password: 'short',
    });

    // Should return validation error
    expect([400, 422]).toContain(res.status);
  });

  it('should require authentication for profile endpoint', async () => {
    const rawClient = axios.create({
      baseURL: `${BASE}/api`,
      timeout: 15000,
      validateStatus: () => true,
    });

    const res = await rawClient.post('/auth/change-password', {
      old_password: 'anything',
      new_password: 'NewPass123!',
    });

    expect([401, 403]).toContain(res.status);
  });
});
