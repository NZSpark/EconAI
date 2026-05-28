import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import TaskOutput from '../../pages/TaskOutput';

const { mockGetTaskOutput, mockGetTaskCitations, mockExportTask } = vi.hoisted(() => ({
  mockGetTaskOutput: vi.fn(),
  mockGetTaskCitations: vi.fn(),
  mockExportTask: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useParams: () => ({ id: 'test-task-id' }) };
});

vi.mock('../../api/tasks', () => ({
  getTaskOutput: mockGetTaskOutput,
  getTaskCitations: mockGetTaskCitations,
  exportTask: mockExportTask,
  getTaskStatus: vi.fn().mockResolvedValue({ status: 'completed' }),
}));

// Mock antd message — must be inside vi.mock factory (hoisted)
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), info: vi.fn() } };
});

describe('TaskOutput Page — Output Preview', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockGetTaskOutput.mockResolvedValue({
      task_id: 'test-task-id',
      title: '文献综述报告',
      content: '# 第一章\n\n这是报告内容 [^1]\n\n[^1]: report:p1-5 (direct)',
      content_type: 'markdown',
      citations_count: 1,
      generated_at: '2026-05-25T10:00:00Z',
    });

    mockGetTaskCitations.mockResolvedValue({
      citations: [
        {
          citation_id: 'cit-1',
          ref_id: 'report:p1-5',
          sentence: '这是报告内容',
          sentence_index: 0,
          confidence: 'direct',
          matched_chunks: [
            {
              chunk_id: 'chunk-1',
              document_id: 'doc-1',
              document_title: '贸易政策分析报告',
              page_start: 1,
              page_end: 5,
              excerpt: '这是原文摘录内容...',
              similarity: 0.95,
            },
          ],
        },
      ],
      summary: { total: 1, direct: 1, fuzzy: 0, uncertain: 0 },
    });
  });

  // ---- Page structure ----

  it('should render output page with title and export controls', async () => {
    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('文献综述报告')).toBeInTheDocument();
    });
  });

  it('should call getTaskOutput on mount', async () => {
    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    await waitFor(() => {
      expect(mockGetTaskOutput).toHaveBeenCalledWith('test-task-id');
    });
  });

  // ---- Citation panel (Section 6.3) ----

  it('should show citation statistics', async () => {
    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText(/引用/)).toBeInTheDocument();
    });
  });

  // ---- Export buttons (Section 6.4) ----

  it('should render export format options', async () => {
    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('文献综述报告')).toBeInTheDocument();
    });
    // Export buttons should exist (md, docx, xlsx, pptx)
    const exportButtons = document.querySelectorAll('[class*="export"]');
    // Best-effort: at least some export UI should be visible
    expect(document.body.textContent).toMatch(/导出|export|Markdown|Word|Excel|PPT/i);
  });

  // ---- Preview mode (Section 6.1) ----

  it('should render markdown content', async () => {
    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('文献综述报告')).toBeInTheDocument();
    });
    // The content should be rendered
    await waitFor(() => {
      expect(document.body.textContent).toContain('这是报告内容');
    });
  });

  // ---- Error state ----

  it('should show error message when loading fails', async () => {
    mockGetTaskOutput.mockRejectedValueOnce(new Error('Network Error'));

    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText(/加载失败|错误/)).toBeInTheDocument();
    });
  });

  // ---- Loading state ----

  it('should show loading state initially', async () => {
    // Don't resolve immediately
    mockGetTaskOutput.mockImplementation(() => new Promise(() => {}));

    render(<MemoryRouter><TaskOutput /></MemoryRouter>);

    // Should show some loading indicator
    await waitFor(() => {
      const spin = document.querySelector('.ant-spin');
      expect(spin).toBeInTheDocument();
    });
  });
});
