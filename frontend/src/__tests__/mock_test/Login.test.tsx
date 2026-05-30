import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Login from '../../pages/Login';

vi.mock('../../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    login: vi.fn(),
    isAuthenticated: false,
    isLoading: false,
  })),
}));

import { useAuth } from '../../hooks/useAuth';

describe('Login Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render login form', () => {
    render(<MemoryRouter><Login /></MemoryRouter>);
    expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('密码')).toBeInTheDocument();
  });

  it('should show PolicyAI title', () => {
    render(<MemoryRouter><Login /></MemoryRouter>);
    expect(screen.getByText('PolicyAI')).toBeInTheDocument();
    expect(screen.getByText('智能经济政策分析平台')).toBeInTheDocument();
  });

  it('should call login on form submit', async () => {
    const mockFn = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      login: mockFn, isAuthenticated: false, isLoading: false,
      user: null, logout: vi.fn(), isAdmin: false, hasForcePasswordChange: false,
      changePassword: vi.fn(),
    } as never);

    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByPlaceholderText('用户名'), 'admin');
    await userEvent.type(screen.getByPlaceholderText('密码'), 'Admin@123');

    // Submit form by pressing Enter
    await userEvent.type(screen.getByPlaceholderText('密码'), '{Enter}');

    await waitFor(() => {
      expect(mockFn).toHaveBeenCalledWith('admin', 'Admin@123');
    });
  });
});
