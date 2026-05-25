import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import KnowledgeBase from '../../pages/KnowledgeBase';

const { mockListDocs, mockDeleteDoc, mockReindexDoc, mockGetDoc, mockGetDocContent, mockSearchKB } =
  vi.hoisted(() => ({
    mockListDocs: vi.fn(),
    mockDeleteDoc: vi.fn(),
    mockReindexDoc: vi.fn(),
    mockGetDoc: vi.fn(),
    mockGetDocContent: vi.fn(),
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
  reindexDocument: mockReindexDoc,
  getDocument: mockGetDoc,
  getDocumentContent: mockGetDocContent,
}));

vi.mock('../../api/search', () => ({
  searchProjectKB: mockSearchKB,
}));

// Shared helper: render KB inside MemoryRouter
function renderKB() {
  return render(
    <MemoryRouter>
      <KnowledgeBase />
    </MemoryRouter>
  );
}

// Shared fixture
function makeDoc(
  docId: string,
  name: string,
  format: string,
  size: number,
  status: string,
  chunkCount = 0,
  pageCount = 0
) {
  return {
    document_id: docId,
    original_name: name,
    format,
    size_bytes: size,
    page_count: pageCount,
    parse_status: status,
    metadata: {},
    is_internal: false,
    chunk_count: chunkCount,
    created_at: '2026-05-01T00:00:00Z',
  };
}

describe('KnowledgeBase Page — Document List', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListDocs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
  });

  // ---- Page structure ----

  it('should render knowledge base page with title and actions', async () => {
    renderKB();

    await waitFor(() => {
      expect(screen.getByText('文档列表')).toBeInTheDocument();
    });
    expect(screen.getByText('上传文档')).toBeInTheDocument();
    expect(screen.getByText('刷新')).toBeInTheDocument();
    expect(screen.getByText('知识库搜索')).toBeInTheDocument();
  });

  // ---- Empty state ----

  it('should show empty state when no documents exist', async () => {
    renderKB();

    await waitFor(() => {
      expect(screen.getByText('暂无文档，请上传')).toBeInTheDocument();
    });
  });

  // ---- Table rendering ----

  it('should display documents in table with multiple statuses', async () => {
    mockListDocs.mockResolvedValueOnce({
      items: [
        makeDoc('doc-1', '贸易政策分析报告.pdf', 'pdf', 1048576, 'ready', 90, 45),
        makeDoc('doc-2', '数据表格.xlsx', 'xlsx', 512000, 'pending', 0, 0),
        makeDoc('doc-3', '待解析文档.docx', 'docx', 256000, 'parsing', 0, 5),
        makeDoc('doc-4', '失败文档.ppt', 'ppt', 128000, 'error', 0, 10),
      ],
      total: 4,
      page: 1,
      page_size: 10,
    });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('贸易政策分析报告.pdf')).toBeInTheDocument();
    });
    expect(screen.getByText('就绪')).toBeInTheDocument();
    expect(screen.getByText('等待中')).toBeInTheDocument();
    expect(screen.getByText('解析中')).toBeInTheDocument();
    expect(screen.getByText('解析失败')).toBeInTheDocument();
    expect(screen.getByText('1.0 MB')).toBeInTheDocument();
  });

  // ---- Pagination info ----

  it('should show pagination total', async () => {
    mockListDocs.mockResolvedValueOnce({
      items: [makeDoc('doc-1', 'test.pdf', 'pdf', 1024, 'ready')],
      total: 25,
      page: 1,
      page_size: 10,
    });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText(/共 25 个文档/)).toBeInTheDocument();
    });
  });

  // ---- Status filter ----

  it('should render status filter select', async () => {
    renderKB();

    await waitFor(() => {
      expect(screen.getByText('文档列表')).toBeInTheDocument();
    });
    // Status filter exists
    expect(document.querySelector('.ant-select')).toBeInTheDocument();
  });

  // ---- Action buttons in row ----

  it('should render detail, content, reindex and delete buttons for ready documents', async () => {
    mockListDocs.mockResolvedValueOnce({
      items: [makeDoc('doc-1', 'ready-doc.pdf', 'pdf', 1024, 'ready', 50, 30)],
      total: 1,
      page: 1,
      page_size: 10,
    });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('ready-doc.pdf')).toBeInTheDocument();
    });
    expect(screen.getByText('详情')).toBeInTheDocument();
    expect(screen.getByText('内容')).toBeInTheDocument();
    expect(screen.getByText('重索引')).toBeInTheDocument();
    expect(screen.getByText('删除')).toBeInTheDocument();
  });

  it('should NOT show content/reindex buttons for non-ready documents', async () => {
    mockListDocs.mockResolvedValueOnce({
      items: [makeDoc('doc-1', 'pending-doc.pdf', 'pdf', 1024, 'pending')],
      total: 1,
      page: 1,
      page_size: 10,
    });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('pending-doc.pdf')).toBeInTheDocument();
    });
    // These buttons should NOT be present for non-ready docs
    expect(screen.queryByText('重索引')).not.toBeInTheDocument();
    expect(screen.queryByText('内容')).not.toBeInTheDocument();
    // Detail and delete should still exist
    expect(screen.getByText('详情')).toBeInTheDocument();
    expect(screen.getByText('删除')).toBeInTheDocument();
  });

  // ---- Delete document ----

  it('should show delete confirmation popover and confirm deletion', async () => {
    mockDeleteDoc.mockResolvedValueOnce(undefined);
    mockListDocs
      .mockResolvedValueOnce({
        items: [makeDoc('doc-1', 'to-delete.pdf', 'pdf', 1024, 'ready')],
        total: 1,
        page: 1,
        page_size: 10,
      })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('to-delete.pdf')).toBeInTheDocument();
    });

    // Click "删除" button — after Popconfirm, the confirm dialog appears
    const deleteBtn = screen.getByText('删除');
    await userEvent.click(deleteBtn);

    // Popconfirm should show; click "确认"
    await waitFor(() => {
      const confirmBtn = screen.getByText('确认');
      expect(confirmBtn).toBeInTheDocument();
    });
    await userEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      expect(mockDeleteDoc).toHaveBeenCalledWith('test-project-id', 'doc-1');
    });
  });

  // ---- Reindex document ----

  it('should trigger reindex when clicking 重索引', async () => {
    mockReindexDoc.mockResolvedValueOnce(undefined);
    mockListDocs
      .mockResolvedValueOnce({
        items: [makeDoc('doc-1', 'reindex-me.pdf', 'pdf', 1024, 'ready', 10, 5)],
        total: 1,
        page: 1,
        page_size: 10,
      })
      .mockResolvedValueOnce({
        items: [makeDoc('doc-1', 'reindex-me.pdf', 'pdf', 1024, 'ready', 10, 5)],
        total: 1,
        page: 1,
        page_size: 10,
      });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('reindex-me.pdf')).toBeInTheDocument();
    });

    const reindexBtn = screen.getByText('重索引');
    await userEvent.click(reindexBtn);

    await waitFor(() => {
      expect(mockReindexDoc).toHaveBeenCalledWith('test-project-id', 'doc-1');
    });
  });

  // ---- View detail ----

  it('should open detail drawer when clicking 详情', async () => {
    mockGetDoc.mockResolvedValueOnce(
      makeDoc('doc-1', 'detail-doc.pdf', 'pdf', 2048, 'ready', 100, 50)
    );
    mockListDocs.mockResolvedValueOnce({
      items: [makeDoc('doc-1', 'detail-doc.pdf', 'pdf', 2048, 'ready', 100, 50)],
      total: 1,
      page: 1,
      page_size: 10,
    });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('detail-doc.pdf')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('详情'));

    await waitFor(() => {
      expect(mockGetDoc).toHaveBeenCalledWith('test-project-id', 'doc-1');
    });
  });

  // ---- View content ----

  it('should open content modal when clicking 内容', async () => {
    mockGetDocContent.mockResolvedValueOnce({
      document_id: 'doc-1',
      original_name: 'content-doc.pdf',
      format: 'pdf',
      content_type: 'text',
      text: 'This is the document content.',
      page_count: 10,
      chunk_count: 30,
    });
    mockListDocs.mockResolvedValueOnce({
      items: [makeDoc('doc-1', 'content-doc.pdf', 'pdf', 2048, 'ready', 30, 10)],
      total: 1,
      page: 1,
      page_size: 10,
    });

    renderKB();

    await waitFor(() => {
      expect(screen.getByText('content-doc.pdf')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('内容'));

    await waitFor(() => {
      expect(mockGetDocContent).toHaveBeenCalledWith('test-project-id', 'doc-1');
    });
  });

  // ---- Error state ----

  it('should show error message when listDocuments fails', async () => {
    mockListDocs.mockRejectedValueOnce(new Error('Network Error'));

    renderKB();

    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    });
  });

  // ---- Search ----

  it('should render search input', async () => {
    renderKB();

    await waitFor(() => {
      expect(screen.getByPlaceholderText('输入搜索关键词...')).toBeInTheDocument();
    });
  });

  it('should display search results', async () => {
    mockSearchKB.mockResolvedValueOnce({
      results: [
        {
          chunk_id: 'chunk-1',
          document_id: 'doc-1',
          document_title: '贸易政策分析.pdf',
          content: '贸易壁垒是限制自由贸易的重要因素...',
          chunk_type: 'paragraph',
          score: 0.92,
          metadata: {
            page_start: 3,
            page_end: 3,
            section_title: '第二章 贸易壁垒',
            paragraph_index: 0,
          },
        },
      ],
      total_hits: 1,
      search_time_ms: 45,
    });

    renderKB();

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
