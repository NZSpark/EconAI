import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import TaskList from '../../pages/TaskList';

const { mockListTasks, mockCreateTask, mockListDocs } = vi.hoisted(() => ({
  mockListTasks: vi.fn(),
  mockCreateTask: vi.fn(),
  mockListDocs: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useParams: () => ({ id: 'test-project-id' }) };
});

vi.mock('../../api/tasks', () => ({
  listTasks: mockListTasks,
  createTask: mockCreateTask,
  cancelTask: vi.fn(),
  retryTask: vi.fn(),
}));

vi.mock('../../api/documents', () => ({
  listDocuments: mockListDocs,
}));

describe('TaskList - Task Creation Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockListTasks.mockResolvedValue({
      items: [], total: 0, page: 1, page_size: 10,
    });

    mockListDocs.mockResolvedValue({
      items: [
        {
          document_id: 'doc-1', original_name: '政策文件1.pdf', format: 'pdf',
          size_bytes: 1000, page_count: 30, parse_status: 'ready',
          metadata: {}, is_internal: false, chunk_count: 60, created_at: '2026-05-01T00:00:00Z',
        },
        {
          document_id: 'doc-2', original_name: '研究报告.docx', format: 'docx',
          size_bytes: 2000, page_count: 15, parse_status: 'ready',
          metadata: {}, is_internal: false, chunk_count: 30, created_at: '2026-05-02T00:00:00Z',
        },
      ],
      total: 2, page: 1, page_size: 200,
    });
  });

  it('should render task list page', async () => {
    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('任务列表')).toBeInTheDocument();
    });
    expect(screen.getByText('创建任务')).toBeInTheDocument();
    expect(screen.getByText('刷新')).toBeInTheDocument();
  });

  it('should open create task modal', async () => {
    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('创建任务')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /创建任务/ }));

    await waitFor(() => {
      expect(screen.getByText('创建分析任务')).toBeInTheDocument();
    });
    expect(screen.getByText('任务类型')).toBeInTheDocument();
    expect(screen.getByText('任务标题')).toBeInTheDocument();
  });

  it('should display all form fields in create modal', async () => {
    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('创建任务')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /创建任务/ }));

    await waitFor(() => {
      expect(screen.getByText('创建分析任务')).toBeInTheDocument();
    });

    expect(screen.getByText('任务类型')).toBeInTheDocument();
    expect(screen.getByText('任务标题')).toBeInTheDocument();
    expect(screen.getByText('输出格式')).toBeInTheDocument();
    expect(screen.getByText('知识源文档')).toBeInTheDocument();
    expect(screen.getByText('分析参数（JSON）')).toBeInTheDocument();
  });

  it('should call listTasks on mount', async () => {
    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(mockListTasks).toHaveBeenCalledWith('test-project-id', {
        page: 1, page_size: 10, status: undefined, type: undefined,
      });
    });
  });

  it('should show empty state', async () => {
    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('暂无任务，点击按钮创建')).toBeInTheDocument();
    });
  });

  it('should display tasks in table', async () => {
    mockListTasks.mockResolvedValueOnce({
      items: [
        {
          task_id: 'task-1', type: 'literature_review', title: '文献综述测试',
          status: 'completed', progress: null, created_by: 'user-1', created_at: '2026-05-19T10:00:00Z',
        },
        {
          task_id: 'task-2', type: 'policy_draft', title: '政策草案测试',
          status: 'running',
          progress: { step: 'generating', step_index: 2, total_steps_estimate: 8, message: '正在生成...' },
          created_by: 'user-1', created_at: '2026-05-20T09:00:00Z',
        },
      ],
      total: 2, page: 1, page_size: 10,
    });

    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('文献综述测试')).toBeInTheDocument();
    });
    expect(screen.getByText('政策草案测试')).toBeInTheDocument();
    expect(screen.getByText('文献综述')).toBeInTheDocument();
    expect(screen.getByText('政策草案')).toBeInTheDocument();
  });

  it('should load documents when create modal opens', async () => {
    render(<MemoryRouter><TaskList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('创建任务')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /创建任务/ }));

    await waitFor(() => {
      expect(screen.getByText('知识源文档')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(mockListDocs).toHaveBeenCalledWith('test-project-id', {
        page: 1, page_size: 200, status: 'ready',
      });
    });
  });
});
