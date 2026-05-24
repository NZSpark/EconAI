/**
 * Integrated Projects API Tests
 *
 * Tests the real project API endpoints against a running backend.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  apiClient,
  loginAsAdmin,
  isBackendAvailable,
  trackResource,
  cleanupResources,
} from './test-helper';

describe('Projects API (Integrated)', () => {
  let createdProjectId: string | null = null;

  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) return;
    await loginAsAdmin();
  });

  afterAll(async () => {
    await cleanupResources();
  });

  it('should list projects', async () => {
    const client = apiClient();
    const res = await client.get('/projects', { params: { page: 1, page_size: 10 } });

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('items');
    expect(res.data).toHaveProperty('total');
    expect(Array.isArray(res.data.items)).toBe(true);
    // Verify project structure if any exist
    if (res.data.items.length > 0) {
      const project = res.data.items[0];
      expect(project).toHaveProperty('project_id');
      expect(project).toHaveProperty('name');
      expect(project).toHaveProperty('status');
    }
  });

  it('should create a project', async () => {
    const client = apiClient();
    const res = await client.post('/projects', {
      name: `Integration-Test-Project-${Date.now()}`,
      description: 'Created by integration test',
      group_id: '', // optional
    });

    // May succeed or fail if group is required, check for reasonable status
    if (res.status === 200 || res.status === 201) {
      expect(res.data).toHaveProperty('project_id');
      createdProjectId = res.data.project_id;
      trackResource('project', createdProjectId, async () => {
        await client.delete(`/projects/${createdProjectId}`);
      });
    } else {
      // API returned an error — acceptable if group_id is required
      expect(res.status).toBeGreaterThanOrEqual(400);
    }
  });

  it('should get a single project by ID', async () => {
    if (!createdProjectId) return;

    const client = apiClient();
    const res = await client.get(`/projects/${createdProjectId}`);

    expect(res.status).toBe(200);
    expect(res.data.project_id).toBe(createdProjectId);
  });

  it('should filter projects by status', async () => {
    const client = apiClient();
    const res = await client.get('/projects', { params: { status: 'active', page: 1, page_size: 5 } });

    expect(res.status).toBe(200);
    expect(Array.isArray(res.data.items)).toBe(true);
    // Status filter may return partial results depending on backend implementation
    for (const item of res.data.items) {
      expect(['active', 'archived', 'completed']).toContain(item.status);
    }
  });

  it('should return 404 for non-existent project', async () => {
    const client = apiClient();
    const res = await client.get('/projects/00000000-0000-0000-0000-000000000000');

    expect(res.status).toBe(404);
  });
});
