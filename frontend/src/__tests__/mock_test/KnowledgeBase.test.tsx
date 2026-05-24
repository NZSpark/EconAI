import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import KnowledgeBase from '../../pages/KnowledgeBase';

const { mockListDocs, mockDeleteDoc, mockSearchKB } = vi.hoisted(() => ({
  mockListDocs: vi.fn(),
  mockDeleteDoc: vi.fn(),
  mockSearchKB: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useParams: () => ({ id: 'test-project-id' }) };
});

vi.mock('../../api/documents', () => ({
  listDocuments: mockListDocs,
  uploadDocument: vi.fn(),
  deleteDocument: mockDeleteDoc,
  reindexDocument: vi.fn(),
  getDocument: vi.fn(),
}));

vi.mock('../../api/search', () => ({
  searchProjectKB: mockSearchKB,
}));

describe('KnowledgeBase Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListDocs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
  });

  it('should render knowledge base page', async () => {
    render(<MemoryRouter><KnowledgeBase /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('文档列表')).toBeInTheDocument();
    });
    expect(screen.getByText('上传文档')).toBeInTheDocument();
    expect(screen.getByText('知识库搜索')).toBeInTheDocument();
  });

  it('should show empty state', async () => {
    render(<MemoryRouter><KnowledgeBase /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('暂无文档，请上传')).toBeInTheDocument();
    });
  });

  it('should display documents in table', async () => {
    mockListDocs.mockResolvedValueOnce({
      items: [
        {
          document_id: 'doc-1', original_name: '贸易政策分析报告.pdf', format: 'pdf',
          size_bytes: 1048576, page_count: 45, parse_status: 'ready',
          metadata: { title: '贸易政策分析', authors: '张三' },
          is_internal: false, chunk_count: 90, created_at: '2026-05-01T00:00:00Z',
        },
        {
          document_id: 'doc-2', original_name: '数据表格.xlsx', format: 'xlsx',
          size_bytes: 512000, page_count: 0, parse_status: 'pending',
          metadata: {}, is_internal: false, chunk_count: 0, created_at: '2026-05-02T00:00:00Z',
        },
      ],
      total: 2, page: 1, page_size: 10,
    });

    render(<MemoryRouter><KnowledgeBase /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('贸易政策分析报告.pdf')).toBeInTheDocument();
    });
    expect(screen.getByText('就绪')).toBeInTheDocument();
    expect(screen.getByText('1.0 MB')).toBeInTheDocument();
  });

  it('should render search input', async () => {
    render(<MemoryRouter><KnowledgeBase /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('输入搜索关键词...')).toBeInTheDocument();
    });
  });

  it('should display search results', async () => {
    mockSearchKB.mockResolvedValueOnce({
      results: [
        {
          chunk_id: 'chunk-1', document_id: 'doc-1', document_title: '贸易政策分析.pdf',
          content: '贸易壁垒是限制自由贸易的重要因素...', chunk_type: 'paragraph',
          score: 0.92,
          metadata: { page_start: 3, page_end: 3, section_title: '第二章 贸易壁垒', paragraph_index: 0 },
        },
      ],
      total_hits: 1, search_time_ms: 45,
    });

    render(<MemoryRouter><KnowledgeBase /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('输入搜索关键词...')).toBeInTheDocument();
    });

    await userEvent.type(screen.getByPlaceholderText('输入搜索关键词...'), '贸易壁垒');
    await userEvent.click(screen.getByRole('button', { name: 'search' }));

    await waitFor(() => {
      expect(screen.getByText(/贸易壁垒是限制自由贸易的重要因素/)).toBeInTheDocument();
    });
  });
});
