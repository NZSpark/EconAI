import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import GroupManagement from '../../pages/Admin/GroupManagement';

const { mockListGroups, mockListMembers, mockSearchNonMembers } = vi.hoisted(() => ({
  mockListGroups: vi.fn(),
  mockListMembers: vi.fn(),
  mockSearchNonMembers: vi.fn(),
}));

vi.mock('../../api/admin', () => ({
  listGroups: mockListGroups,
  createGroup: vi.fn(),
  listGroupMembers: mockListMembers,
  searchNonGroupMembers: mockSearchNonMembers,
  addGroupMember: vi.fn(),
  removeGroupMember: vi.fn(),
}));

describe('GroupManagement Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockListGroups.mockResolvedValue({
      items: [],
      total: 0, page: 1, page_size: 10,
    });

    mockListMembers.mockResolvedValue([]);
    mockSearchNonMembers.mockResolvedValue([]);
  });

  it('should render group management page', async () => {
    render(<MemoryRouter><GroupManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('项目组管理')).toBeInTheDocument();
    });
    expect(screen.getByText('创建项目组')).toBeInTheDocument();
  });

  it('should display groups in table', async () => {
    mockListGroups.mockResolvedValueOnce({
      items: [
        { group_id: 'g1', name: '贸易政策研究组', description: '研究', member_count: 3, created_at: '2026-01-01T00:00:00Z' },
        { group_id: 'g2', name: '数据分析组', description: '', member_count: 1, created_at: '2026-01-02T00:00:00Z' },
      ],
      total: 2, page: 1, page_size: 10,
    });

    render(<MemoryRouter><GroupManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('贸易政策研究组')).toBeInTheDocument();
    });
    expect(screen.getByText('数据分析组')).toBeInTheDocument();
  });

  it('should open create group modal', async () => {
    const { container } = render(<MemoryRouter><GroupManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('项目组管理')).toBeInTheDocument();
    });
    const createBtn = container.querySelector('.ant-btn-primary') as HTMLElement;
    await userEvent.click(createBtn);

    await waitFor(() => {
      const modal = document.querySelector('.ant-modal-title');
      expect(modal?.textContent).toBe('创建项目组');
    });
  });

  it('should open manage members modal', async () => {
    mockListGroups.mockResolvedValueOnce({
      items: [
        { group_id: 'g1', name: '测试组', description: '', member_count: 2, created_at: '' },
      ],
      total: 1, page: 1, page_size: 10,
    });
    mockListMembers.mockResolvedValue([
      { user_id: 'u1', username: 'user1', display_name: '用户一', role: 'analyst' },
    ]);

    render(<MemoryRouter><GroupManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('管理成员')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByText('管理成员'));

    await waitFor(() => {
      expect(screen.getByText('user1')).toBeInTheDocument();
    });
  });

  it('should show member search input', async () => {
    mockListGroups.mockResolvedValueOnce({
      items: [
        { group_id: 'g1', name: '测试组', description: '', member_count: 0, created_at: '' },
      ],
      total: 1, page: 1, page_size: 10,
    });

    render(<MemoryRouter><GroupManagement /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('管理成员')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByText('管理成员'));

    // 检查 Modal 中是否显示搜索输入和添加按钮
    await waitFor(() => {
      const modal = document.querySelector('.ant-modal-body');
      expect(modal?.textContent).toContain('添加成员');
    });
  });
});
