import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Profile from '../../pages/Profile';

const { mockChangePassword } = vi.hoisted(() => ({
  mockChangePassword: vi.fn(),
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      user_id: 'u1', username: 'testuser', display_name: '测试用户',
      role: 'analyst', groups: [],
    },
    hasForcePasswordChange: false,
    changePassword: mockChangePassword,
    logout: vi.fn(),
    isAuthenticated: true,
  }),
}));

describe('Profile Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render profile page with user info', async () => {
    render(<MemoryRouter><Profile /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('个人设置')).toBeInTheDocument();
    });
    expect(screen.getByText('testuser')).toBeInTheDocument();
    expect(screen.getByText('测试用户')).toBeInTheDocument();
    expect(screen.getByText('分析员')).toBeInTheDocument();
  });

  it('should render password change form', async () => {
    render(<MemoryRouter><Profile /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('输入当前密码')).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText('输入新密码（至少8位）')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('再次输入新密码')).toBeInTheDocument();
  });

  it('should validate password mismatch', async () => {
    render(<MemoryRouter><Profile /></MemoryRouter>);

    await userEvent.type(screen.getByPlaceholderText('输入当前密码'), 'old');
    await userEvent.type(screen.getByPlaceholderText('输入新密码（至少8位）'), 'pass1');
    // type in confirm field triggers form validation
    const confirmInput = screen.getByPlaceholderText('再次输入新密码');
    await userEvent.type(confirmInput, 'pass2');
    // blur to trigger validation
    await userEvent.tab();

    await waitFor(() => {
      expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument();
    });
  });

  it('should call changePassword on submit', async () => {
    mockChangePassword.mockResolvedValue(undefined);

    render(<MemoryRouter><Profile /></MemoryRouter>);

    await userEvent.type(screen.getByPlaceholderText('输入当前密码'), 'oldpass');
    await userEvent.type(screen.getByPlaceholderText('输入新密码（至少8位）'), 'newpass1');
    await userEvent.type(screen.getByPlaceholderText('再次输入新密码'), 'newpass1');
    await userEvent.click(screen.getByRole('button', { name: /修改密码/ }));

    await waitFor(() => {
      expect(mockChangePassword).toHaveBeenCalledWith('oldpass', 'newpass1');
    });
  });

  it('should enforce min password length', async () => {
    render(<MemoryRouter><Profile /></MemoryRouter>);

    await userEvent.type(screen.getByPlaceholderText('输入新密码（至少8位）'), 'short');
    await userEvent.tab();

    await waitFor(() => {
      expect(screen.getByText('密码至少8位')).toBeInTheDocument();
    });
  });
});
