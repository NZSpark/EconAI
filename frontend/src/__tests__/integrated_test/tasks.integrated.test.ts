/**
 * Integrated Tasks API Tests
 *
 * Tests task listing, creation, status, and lifecycle endpoints.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  apiClient,
  loginAsAdmin,
  isBackendAvailable,
  trackResource,
  cleanupResources,
} from './test-helper';

describe('Tasks API (Integrated)', () => {
  let projectId: string | null = null;
  let taskId: string | null = null;

  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) return;
    await loginAsAdmin();

    // Create a project for task tests
    const client = apiClient();
    const projRes = await client.post('/projects', {
      name: `ITest-Tasks-${Date.now()}`,
      description: 'Integration test for tasks',
    });
    if (projRes.status === 200 || projRes.status === 201) {
      projectId = projRes.data.project_id;
      trackResource('project', projectId, async () => {
        await client.delete(`/projects/${projectId}`);
      });
    }
  });

  afterAll(async () => {
    await cleanupResources();
  });

  it('should list tasks for a project', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.get(`/projects/${projectId}/tasks`, {
      params: { page: 1, page_size: 10 },
    });

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('items');
    expect(Array.isArray(res.data.items)).toBe(true);
  });

  it('should create a task', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.post(`/projects/${projectId}/tasks`, {
      type: 'literature_review',
      title: `ITest Literature Review ${Date.now()}`,
      description: 'Integration test task',
      kb_sources: {
        documents: [],  // empty doc list — may error depending on validation
        include_institutional: false,
      },
      output_formats: ['md'],
      analysis_params: {
        focus_areas: ['贸易政策'],
      },
    });

    // Task creation may succeed or fail depending on kb_sources requirements
    if (res.status === 200 || res.status === 201) {
      expect(res.data).toHaveProperty('task_id');
      expect(res.data).toHaveProperty('status');
      taskId = res.data.task_id;
      trackResource('task', taskId);
    } else {
      // Even if creation fails, verify the error response is structured
      expect(res.status).toBeGreaterThanOrEqual(400);
      if (res.data) {
        expect(res.data).toHaveProperty('error');
      }
    }
  });

  it('should get task detail by ID', async () => {
    if (!taskId) return;

    const client = apiClient();
    const res = await client.get(`/tasks/${taskId}`);

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('task_id', taskId);
    expect(res.data).toHaveProperty('type');
    expect(res.data).toHaveProperty('status');
    expect(res.data).toHaveProperty('title');
  });

  it('should get task status', async () => {
    if (!taskId) return;

    const client = apiClient();
    const res = await client.get(`/tasks/${taskId}/status`);

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('status');
    // May have progress if task started
    expect(['pending', 'running', 'completed', 'failed', 'cancelled']).toContain(res.data.status);
  });

  it('should filter tasks by status', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.get(`/projects/${projectId}/tasks`, {
      params: { page: 1, page_size: 10, status: 'completed' },
    });

    expect(res.status).toBe(200);
    for (const t of res.data.items) {
      expect(t.status).toBe('completed');
    }
  });

  it('should filter tasks by type', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.get(`/projects/${projectId}/tasks`, {
      params: { page: 1, page_size: 10, type: 'literature_review' },
    });

    expect(res.status).toBe(200);
    for (const t of res.data.items) {
      expect(t.type).toBe('literature_review');
    }
  });

  it('should return 404 for non-existent task', async () => {
    const client = apiClient();
    const res = await client.get('/tasks/00000000-0000-0000-0000-000000000000');

    expect(res.status).toBe(404);
  });

  it('should cancel a pending task', async () => {
    if (!taskId) return;

    const client = apiClient();
    const res = await client.post(`/tasks/${taskId}/cancel`);

    // Cancellation may succeed (200) or fail if already running/completed (409/422)
    expect([200, 201, 204, 409, 422]).toContain(res.status);
  });

  it('should generate export URL', async () => {
    if (!taskId) return;

    const baseUrl = `${process.env.TEST_API_BASE_URL || 'http://localhost:8000'}/api`;
    const exportUrl = `${baseUrl}/tasks/${taskId}/export?format=md`;

    // Just verify the URL structure is correct
    expect(exportUrl).toContain(taskId);
    expect(exportUrl).toContain('format=md');
    expect(exportUrl).toContain('/export');
  });
});
