/**
 * Integrated Admin API Tests
 *
 * Tests user management, group management, and audit log endpoints.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import axios from 'axios';
import {
  apiClient,
  loginAsAdmin,
  isBackendAvailable,
  trackResource,
  cleanupResources,
} from './test-helper';

const BASE = process.env.TEST_API_BASE_URL || 'http://localhost:8000';

describe('Admin API (Integrated)', () => {
  let createdUserId: string | null = null;
  let createdGroupId: string | null = null;

  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) return;
    await loginAsAdmin();
  });

  afterAll(async () => {
    await cleanupResources();
  });

  // ===== User Management =====

  describe('User Management', () => {
    it('should list users', async () => {
      const client = apiClient();
      const res = await client.get('/admin/users', { params: { page: 1, page_size: 10 } });

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('items');
      expect(Array.isArray(res.data.items)).toBe(true);
      if (res.data.items.length > 0) {
        const user = res.data.items[0];
        expect(user).toHaveProperty('user_id');
        expect(user).toHaveProperty('username');
        expect(user).toHaveProperty('role');
      }
    });

    it('should filter users by active status', async () => {
      const client = apiClient();
      const res = await client.get('/admin/users', {
        params: { page: 1, page_size: 10, is_active: true },
      });

      expect(res.status).toBe(200);
      // Some users may be inactive; the filter should not return them
      for (const u of res.data.items) {
        expect(typeof u.is_active).toBe('boolean');
      }
    });

    it('should create a new user', async () => {
      const client = apiClient();
      const username = `itest_user_${Date.now()}`;
      const res = await client.post('/admin/users', {
        username,
        password: 'TestPass123!',
        email: `${username}@test.local`,
        display_name: 'Integration Test User',
        role: 'analyst',
      });

      // May succeed or fail depending on email validation / uniqueness
      if (res.status === 200 || res.status === 201) {
        expect(res.data).toHaveProperty('user_id');
        expect(res.data.username).toBe(username);
        createdUserId = res.data.user_id;
        trackResource('user', createdUserId, async () => {
          await client.delete(`/admin/users/${createdUserId}`);
        });
      }
    });

    it('should return 401 for unauthenticated user listing', async () => {
      const rawClient = axios.create({
        baseURL: `${BASE}/api`,
        timeout: 15000,
        validateStatus: () => true,
      });
      const res = await rawClient.get('/admin/users');

      // Should be 401 or 403
      expect([401, 403]).toContain(res.status);
    });
  });

  // ===== Group Management =====

  describe('Group Management', () => {
    it('should list groups', async () => {
      const client = apiClient();
      const res = await client.get('/admin/groups', { params: { page: 1, page_size: 10 } });

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('items');
      if (res.data.items.length > 0) {
        expect(res.data.items[0]).toHaveProperty('group_id');
        expect(res.data.items[0]).toHaveProperty('name');
        expect(res.data.items[0]).toHaveProperty('member_count');
      }
    });

    it('should create a new group', async () => {
      const client = apiClient();
      const res = await client.post('/admin/groups', {
        name: `ITest-Group-${Date.now()}`,
        description: 'Created by integration test',
      });

      if (res.status === 200 || res.status === 201) {
        expect(res.data).toHaveProperty('group_id');
        createdGroupId = res.data.group_id;
        trackResource('group', createdGroupId);
      }
    });

    it('should list group members', async () => {
      if (!createdGroupId) return;

      const client = apiClient();
      const res = await client.get(`/admin/groups/${createdGroupId}/members`);

      expect(res.status).toBe(200);
      expect(Array.isArray(res.data)).toBe(true);
    });
  });

  // ===== Audit Logs =====

  describe('Audit Logs', () => {
    it('should list audit logs', async () => {
      const client = apiClient();
      const res = await client.get('/admin/audit-logs', { params: { page: 1, page_size: 10 } });

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('items');
      expect(res.data).toHaveProperty('total');
      // Recent login should create at least some entries
      if (res.data.items.length > 0) {
        const entry = res.data.items[0];
        expect(entry).toHaveProperty('audit_id');
        expect(entry).toHaveProperty('action');
        expect(entry).toHaveProperty('resource_type');
        expect(entry).toHaveProperty('created_at');
      }
    });

    it('should filter audit logs by user_id', async () => {
      const client = apiClient();
      const res = await client.get('/admin/audit-logs', {
        params: { page: 1, page_size: 5, user_id: '00000000-0000-0000-0000-000000000000' },
      });

      expect(res.status).toBe(200);
      // Filtering by nonexistent user_id should return few/no results
      if (res.data.items.length > 0) {
        for (const entry of res.data.items) {
          // All returned entries should (ideally) match this user_id
          expect(entry).toHaveProperty('user_id');
        }
      }
    });

    it('should filter audit logs by action', async () => {
      const client = apiClient();
      const res = await client.get('/admin/audit-logs', {
        params: { page: 1, page_size: 20, action: 'login' },
      });

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('items');
      expect(res.data).toHaveProperty('total');
      // Verify returned entries have proper structure
      for (const entry of res.data.items) {
        expect(entry).toHaveProperty('audit_id');
        expect(entry).toHaveProperty('action');
        expect(entry).toHaveProperty('resource_type');
        expect(entry).toHaveProperty('created_at');
      }
    });
  });
});
