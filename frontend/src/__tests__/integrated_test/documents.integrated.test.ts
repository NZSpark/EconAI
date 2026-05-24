/**
 * Integrated Documents API Tests
 *
 * Tests document listing, upload, search, and lifecycle endpoints.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { createReadStream, writeFileSync, unlinkSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import FormData from 'form-data';
import {
  apiClient,
  loginAsAdmin,
  isBackendAvailable,
  trackResource,
  cleanupResources,
} from './test-helper';

/** Create a temporary text file for upload tests */
function createTempFile(content: string, filename: string): string {
  const filepath = join(tmpdir(), filename);
  writeFileSync(filepath, content, 'utf-8');
  return filepath;
}

describe('Documents API (Integrated)', () => {
  let projectId: string | null = null;
  let documentId: string | null = null;
  const tempFiles: string[] = [];

  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) return;
    await loginAsAdmin();

    // Create a project for document tests
    const client = apiClient();
    const projRes = await client.post('/projects', {
      name: `ITest-Docs-${Date.now()}`,
      description: 'Integration test for documents',
    });
    if (projRes.status === 200 || projRes.status === 201) {
      projectId = projRes.data.project_id;
      trackResource('project', projectId, async () => {
        await client.delete(`/projects/${projectId}`);
      });
    }
  });

  afterAll(async () => {
    // Clean up temp files
    for (const f of tempFiles) {
      try { unlinkSync(f); } catch { /* ignore */ }
    }
    await cleanupResources();
  });

  it('should list documents (empty project)', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.get(`/projects/${projectId}/documents`, {
      params: { page: 1, page_size: 10 },
    });

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('items');
    expect(Array.isArray(res.data.items)).toBe(true);
  });

  it('should upload a document', async () => {
    if (!projectId) return;

    const content = 'This is a test document for EconAI integration testing.\n贸易政策分析测试文档。\n\n## 第一章\n这是关于贸易壁垒的分析内容。';
    const filepath = createTempFile(content, `itest-doc-${Date.now()}.txt`);
    tempFiles.push(filepath);

    const formData = new FormData();
    formData.append('file', createReadStream(filepath), 'test-document.txt');

    const client = apiClient();
    const res = await client.post(
      `/projects/${projectId}/documents`,
      formData,
      {
        headers: { ...formData.getHeaders() },
        timeout: 120000,
      }
    );

    expect([200, 201]).toContain(res.status);
    expect(res.data).toHaveProperty('document_id');
    expect(res.data).toHaveProperty('parse_status');
    documentId = res.data.document_id;
    trackResource('document', documentId);
  }, 120000);

  it('should get a single document', async () => {
    if (!projectId || !documentId) return;

    const client = apiClient();
    const res = await client.get(`/projects/${projectId}/documents/${documentId}`);

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('document_id', documentId);
    expect(res.data).toHaveProperty('original_name');
    expect(res.data).toHaveProperty('format');
    expect(res.data).toHaveProperty('parse_status');
  });

  it('should search knowledge base in project', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.post(`/projects/${projectId}/search`, {
      query: '贸易政策',
      top_k: 5,
    });

    expect(res.status).toBe(200);
    expect(res.data).toHaveProperty('results');
    expect(res.data).toHaveProperty('total_hits');
  });

  it('should return search results with expected structure', async () => {
    if (!projectId) return;

    const client = apiClient();
    const res = await client.post(`/projects/${projectId}/search`, {
      query: 'test document',
      top_k: 3,
    });

    expect(res.status).toBe(200);
    if (res.data.results.length > 0) {
      const result = res.data.results[0];
      expect(result).toHaveProperty('chunk_id');
      expect(result).toHaveProperty('document_id');
      expect(result).toHaveProperty('content');
      expect(result).toHaveProperty('score');
    }
  });

  it('should return empty or 404 for non-existent project documents', async () => {
    const client = apiClient();
    const res = await client.get('/projects/00000000-0000-0000-0000-000000000000/documents');

    // Backend may return 404 or 200 with empty items depending on implementation
    expect([200, 404]).toContain(res.status);
    if (res.status === 200) {
      expect(Array.isArray(res.data.items)).toBe(true);
    }
  });
});
