import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ProjectList from '../../pages/ProjectList';

const { mockListProjects, mockListGroups } = vi.hoisted(() => ({
  mockListProjects: vi.fn(),
  mockListGroups: vi.fn(),
}));

vi.mock('../../api/projects', () => ({
  listProjects: mockListProjects,
  createProject: vi.fn(),
  archiveProject: vi.fn(),
}));

vi.mock('../../api/admin', () => ({
  listGroups: mockListGroups,
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { username: 'admin', role: 'system_admin', display_name: 'Admin' },
    isAuthenticated: true,
  }),
}));

describe('ProjectList Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockListProjects.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
    });

    mockListGroups.mockResolvedValue({
      items: [
        { group_id: 'g1', name: '贸易政策研究组', description: '', member_count: 3, created_at: '' },
      ],
      total: 1,
      page: 1,
      page_size: 200,
    });
  });

  it('should render project list page', async () => {
    render(
      <MemoryRouter>
        <ProjectList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('项目列表')).toBeInTheDocument();
    });
    expect(screen.getByText('创建项目')).toBeInTheDocument();
  });

  it('should show empty state', async () => {
    render(
      <MemoryRouter>
        <ProjectList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('暂无项目，点击按钮创建')).toBeInTheDocument();
    });
  });

  it('should display project data in table', async () => {
    mockListProjects.mockResolvedValueOnce({
      items: [
        {
          project_id: 'p1', name: '2024数字贸易政策', description: '贸易政策相关',
          group_id: 'g1', group_name: '贸易政策研究组', status: 'active' as const,
          document_count: 5, created_by: 'u1',
          created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      total: 1, page: 1, page_size: 10,
    });

    render(<MemoryRouter><ProjectList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('2024数字贸易政策')).toBeInTheDocument();
    });
    expect(screen.getByText('贸易政策研究组')).toBeInTheDocument();
    expect(screen.getByText('活跃')).toBeInTheDocument();
  });

  it('should open create modal', async () => {
    const { container } = render(<MemoryRouter><ProjectList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('创建项目')).toBeInTheDocument();
    });
    // Click the button by finding it in the container
    const createBtn = container.querySelector('.ant-btn-primary') as HTMLElement;
    await userEvent.click(createBtn);

    // Modal should appear in the document (AntD renders to body)
    await waitFor(() => {
      const modal = document.querySelector('.ant-modal-title');
      expect(modal).toBeInTheDocument();
      expect(modal?.textContent).toBe('创建项目');
    });
  });

  it('should show archive button only for active projects', async () => {
    mockListProjects.mockResolvedValueOnce({
      items: [
        { project_id: 'p1', name: '活跃项目', description: '', group_id: 'g1', group_name: '组1', status: 'active' as const, document_count: 0, created_by: 'u1', created_at: '', updated_at: '' },
        { project_id: 'p2', name: '已归档项目', description: '', group_id: 'g1', group_name: '组1', status: 'archived' as const, document_count: 0, created_by: 'u1', created_at: '', updated_at: '' },
      ],
      total: 2, page: 1, page_size: 10,
    });

    render(<MemoryRouter><ProjectList /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('活跃项目')).toBeInTheDocument();
    });
    // 活跃行有"归档"操作按钮，归档行没有。
    // Popconfirm wraps the Button; look for button by text with whitespace normalization
    await waitFor(() => {
      const buttons = screen.getAllByRole('button');
      const archiveBtns = buttons.filter(
        b => b.textContent?.replace(/\s+/g, '') === '归档'
      );
      expect(archiveBtns.length).toBe(1);
    });
  });
});
