import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AuditLogs from '../../pages/Admin/AuditLogs';

const { mockListAuditLogs } = vi.hoisted(() => ({
  mockListAuditLogs: vi.fn(),
}));

vi.mock('../../api/admin', () => ({
  listAuditLogs: mockListAuditLogs,
}));

describe('AuditLogs Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockListAuditLogs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  it('should render audit log page', async () => {
    render(<MemoryRouter><AuditLogs /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });
    expect(screen.getByText('刷新')).toBeInTheDocument();
  });

  it('should display audit log entries', async () => {
    mockListAuditLogs.mockResolvedValueOnce({
      items: [
        {
          audit_id: 'audit-1', user_id: 'u1', username: 'admin', action: 'login',
          resource_type: 'user', resource_id: 'u1', details: { ip: '127.0.0.1' },
          ip_address: '127.0.0.1', user_agent: 'Chrome', created_at: '2026-05-24T10:00:00Z',
        },
        {
          audit_id: 'audit-2', user_id: 'u2', username: 'testuser', action: 'create_project',
          resource_type: 'project', resource_id: 'proj-123', details: { name: '测试' },
          ip_address: '10.0.0.1', user_agent: 'Firefox', created_at: '2026-05-24T11:00:00Z',
        },
      ],
      total: 2, page: 1, page_size: 20,
    });

    render(<MemoryRouter><AuditLogs /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('admin')).toBeInTheDocument();
    });
    expect(screen.getByText('login')).toBeInTheDocument();
    expect(screen.getByText('testuser')).toBeInTheDocument();
    expect(screen.getByText('create_project')).toBeInTheDocument();
  });

  it('should have filter controls', async () => {
    render(<MemoryRouter><AuditLogs /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });
    // 用户ID输入框和查询按钮存在
    expect(screen.getByPlaceholderText('用户ID')).toBeInTheDocument();
    // AntD Button text content may have extra whitespace from icon/spacing
    // Use normalize-space matching
    const queryBtn = screen.getByText((content) =>
      content.replace(/\s+/g, '').includes('查询')
    );
    expect(queryBtn).toBeInTheDocument();
  });

  it('should show resource ID with copy', async () => {
    mockListAuditLogs.mockResolvedValueOnce({
      items: [
        {
          audit_id: 'audit-1', user_id: 'u1', username: 'admin', action: 'upload_document',
          resource_type: 'document', resource_id: '12345678-1234-1234-1234-123456789abc',
          details: null, ip_address: '127.0.0.1', user_agent: '',
          created_at: '2026-05-24T10:00:00Z',
        },
      ],
      total: 1, page: 1, page_size: 20,
    });

    render(<MemoryRouter><AuditLogs /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('12345678...')).toBeInTheDocument();
    });
  });

  it('should show empty state', async () => {
    render(<MemoryRouter><AuditLogs /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('暂无审计日志')).toBeInTheDocument();
    });
  });
});
