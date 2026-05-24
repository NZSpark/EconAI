import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import PrivateRoute from '../../components/PrivateRoute';
import AdminRoute from '../../components/AdminRoute';
import { useAuth } from '../../hooks/useAuth';

// Mock useAuth
vi.mock('../../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

const mockUseAuth = useAuth as ReturnType<typeof vi.fn>;

function renderWithRouter(children: React.ReactNode) {
  return render(<BrowserRouter>{children}</BrowserRouter>);
}

describe('PrivateRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should show loading spinner when auth is loading', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      user: null,
      isAdmin: false,
    });

    renderWithRouter(
      <PrivateRoute>
        <div>Protected Content</div>
      </PrivateRoute>
    );

    // Should show loading state (Spin component)
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });

  it('should redirect to /login when not authenticated', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      isAdmin: false,
    });

    renderWithRouter(
      <PrivateRoute>
        <div>Protected Content</div>
      </PrivateRoute>
    );

    await waitFor(() => {
      // Should have redirected (Navigate component)
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });
  });

  it('should render children when authenticated', async () => {
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

    renderWithRouter(
      <PrivateRoute>
        <div>Protected Content</div>
      </PrivateRoute>
    );

    await waitFor(() => {
      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });
  });
});

describe('AdminRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should show 403 for non-admin users', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        user_id: 'test-uuid',
        username: 'analyst',
        display_name: 'Analyst User',
        role: 'analyst',
        groups: [],
      },
      isAdmin: false,
    });

    renderWithRouter(
      <AdminRoute>
        <div>Admin Content</div>
      </AdminRoute>
    );

    await waitFor(() => {
      expect(screen.queryByText('Admin Content')).not.toBeInTheDocument();
      expect(screen.getByText('403')).toBeInTheDocument();
    });
  });

  it('should allow system_admin to access admin routes', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        user_id: 'admin-uuid',
        username: 'admin',
        display_name: 'Admin',
        role: 'system_admin',
        groups: [],
      },
      isAdmin: true,
    });

    renderWithRouter(
      <AdminRoute>
        <div>Admin Content</div>
      </AdminRoute>
    );

    await waitFor(() => {
      expect(screen.getByText('Admin Content')).toBeInTheDocument();
    });
  });

  it('should redirect to login for unauthenticated users', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      isAdmin: false,
    });

    renderWithRouter(
      <AdminRoute>
        <div>Admin Content</div>
      </AdminRoute>
    );

    await waitFor(() => {
      expect(screen.queryByText('Admin Content')).not.toBeInTheDocument();
    });
  });
});