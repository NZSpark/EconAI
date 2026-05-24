import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import UserManagement from '../../pages/Admin/UserManagement';

const { mockListUsers, mockListGroups } = vi.hoisted(() => ({
  mockListUsers: vi.fn(),
  mockListGroups: vi.fn(),
}));

vi.mock('../../api/admin', () => ({
  listUsers: mockListUsers,
  createUser: vi.fn(),
  updateUser: vi.fn(),
  disableUser: vi.fn(),
  resetUserPassword: vi.fn(),
  listGroups: mockListGroups,
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { username: 'admin', role: 'system_admin' },
    isAuthenticated: true,
  }),
}));

describe('UserManagement Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockListUsers.mockResolvedValue({
      items: [], total: 0, page: 1, page_size: 10,
    });

    mockListGroups.mockResolvedValue({
      items: [{ group_id: 'g1', name: '测试组', description: '', member_count: 1, created_at: '' }],
      total: 1, page: 1, page_size: 200,
    });
  });

  it('should render user management page', async () => {
    render(<MemoryRouter><UserManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('用户管理')).toBeInTheDocument();
    });
    expect(screen.getByText('创建用户')).toBeInTheDocument();
  });

  it('should display users in table', async () => {
    mockListUsers.mockResolvedValueOnce({
      items: [
        {
          user_id: 'u1', username: 'testuser', email: 'test@example.com',
          display_name: '测试用户', role: 'analyst', auth_provider: 'local',
          is_active: true, force_password_change: false, created_at: '2026-01-01T00:00:00Z',
        },
      ],
      total: 1, page: 1, page_size: 10,
    });

    render(<MemoryRouter><UserManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument();
    });
    expect(screen.getByText('测试用户')).toBeInTheDocument();
    expect(screen.getByText('分析员')).toBeInTheDocument();
  });

  it('should show 待改密 tag', async () => {
    mockListUsers.mockResolvedValueOnce({
      items: [
        {
          user_id: 'u1', username: 'newuser', email: 'new@example.com',
          display_name: '新人', role: 'analyst', auth_provider: 'local',
          is_active: true, force_password_change: true, created_at: '2026-01-01T00:00:00Z',
        },
      ],
      total: 1, page: 1, page_size: 10,
    });

    render(<MemoryRouter><UserManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('待改密')).toBeInTheDocument();
    });
  });

  it('should open create user modal', async () => {
    const { container } = render(<MemoryRouter><UserManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('用户管理')).toBeInTheDocument();
    });
    const createBtn = container.querySelector('.ant-btn-primary') as HTMLElement;
    await userEvent.click(createBtn);

    // Modal title should appear
    await waitFor(() => {
      const modal = document.querySelector('.ant-modal-title');
      expect(modal?.textContent).toBe('创建用户');
    });
  });

  it('should show disable button for active users', async () => {
    mockListUsers.mockResolvedValueOnce({
      items: [
        {
          user_id: 'u1', username: 'activeuser', email: 'a@example.com',
          display_name: '活跃用户', role: 'analyst', auth_provider: 'local',
          is_active: true, force_password_change: false, created_at: '2026-01-01T00:00:00Z',
        },
      ],
      total: 1, page: 1, page_size: 10,
    });

    render(<MemoryRouter><UserManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('停用')).toBeInTheDocument();
    });
  });
});
