import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import TaskList from '../pages/TaskList';
import { useAuth } from '../hooks/useAuth';
import * as tasksApi from '../api/tasks';

// Mock modules
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../api/tasks', () => ({
  listTasks: vi.fn(),
  createTask: vi.fn(),
  cancelTask: vi.fn(),
  retryTask: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'test-project-id' }),
  };
});

const mockUseAuth = useAuth as ReturnType<typeof vi.fn>;

describe('TaskList - Task Creation Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        user_id: 'test-uuid',
        username: 'testuser',
        display_name: 'Test User',
        role: 'senior_researcher',
        groups: [],
      },
      isAdmin: false,
    });

    // Mock empty task list
    vi.mocked(tasksApi.listTasks).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
    });
  });

  it('should render task list page', async () => {
    render(
      <MemoryRouter>
        <TaskList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('任务列表')).toBeInTheDocument();
      expect(screen.getByText('创建任务')).toBeInTheDocument();
      expect(screen.getByText('刷新')).toBeInTheDocument();
    });
  });

  it('should open create task modal on button click', async () => {
    render(
      <MemoryRouter>
        <TaskList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('创建任务')).toBeInTheDocument();
    });

    const createBtn = screen.getByText('创建任务');
    await userEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText('创建分析任务')).toBeInTheDocument();
      expect(screen.getByText('任务类型')).toBeInTheDocument();
      expect(screen.getByText('任务标题')).toBeInTheDocument();
    });
  });

  it('should display modal with form fields on create click', async () => {
    render(
      <MemoryRouter>
        <TaskList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('创建任务')).toBeInTheDocument();
    });

    // Open create modal
    await userEvent.click(screen.getByText('创建任务'));

    // Verify modal title and form fields appear
    await waitFor(() => {
      expect(screen.getByText('创建分析任务')).toBeInTheDocument();
    });

    expect(screen.getByText('任务类型')).toBeInTheDocument();
    expect(screen.getByText('任务标题')).toBeInTheDocument();
    expect(screen.getByText('输出格式')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('例如：数字贸易规则对发展中国家的影响综述')
    ).toBeInTheDocument();
  });

  it('should call listTasks on mount', async () => {
    render(
      <MemoryRouter>
        <TaskList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(tasksApi.listTasks).toHaveBeenCalledWith('test-project-id', {
        page: 1,
        page_size: 10,
        status: undefined,
        type: undefined,
      });
    });
  });

  it('should show empty state when no tasks exist', async () => {
    render(
      <MemoryRouter>
        <TaskList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('暂无任务，点击按钮创建')).toBeInTheDocument();
    });
  });

  it('should display tasks in table', async () => {
    vi.mocked(tasksApi.listTasks).mockResolvedValueOnce({
      items: [
        {
          task_id: 'task-1',
          type: 'literature_review',
          title: 'Literature Review Test',
          status: 'completed',
          progress: null,
          created_by: 'user-1',
          created_at: '2026-05-19T10:00:00Z',
        },
        {
          task_id: 'task-2',
          type: 'policy_draft',
          title: 'Policy Draft Test',
          status: 'running',
          progress: {
            step: 'generating',
            step_index: 2,
            total_steps_estimate: 8,
            message: 'Generating section...',
          },
          created_by: 'user-1',
          created_at: '2026-05-20T09:00:00Z',
        },
      ],
      total: 2,
      page: 1,
      page_size: 10,
    });

    render(
      <MemoryRouter>
        <TaskList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Literature Review Test')).toBeInTheDocument();
      expect(screen.getByText('Policy Draft Test')).toBeInTheDocument();
      expect(screen.getByText('文献综述')).toBeInTheDocument();
      expect(screen.getByText('政策草案')).toBeInTheDocument();
    });
  });
});