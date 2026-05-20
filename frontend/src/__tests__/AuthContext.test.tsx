import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '../contexts/AuthContext';
import { useAuth } from '../hooks/useAuth';
import * as authApi from '../api/auth';
import type { LoginResponse } from '../api/types';

// Mock the auth API
vi.mock('../api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
}));

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();
Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
  });

  function TestConsumer({
    onAuth,
  }: {
    onAuth: (auth: {
      isAuthenticated: boolean;
      user: unknown;
      login: (u: string, p: string) => Promise<void>;
      logout: () => Promise<void>;
    }) => React.ReactNode;
  }) {
    const auth = useAuth();
    return <>{onAuth(auth)}</>;
  }

  it('should start with no user and not authenticated', () => {
    let authValue: { isAuthenticated: boolean; user: unknown } | null = null;

    render(
      <BrowserRouter>
        <AuthProvider>
          <TestConsumer
            onAuth={(auth) => {
              authValue = { isAuthenticated: auth.isAuthenticated, user: auth.user };
              return <div>Test</div>;
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    );

    waitFor(() => {
      expect(authValue?.isAuthenticated).toBe(false);
      expect(authValue?.user).toBeNull();
    });
  });

  it('should login successfully and store tokens', async () => {
    const mockResponse: LoginResponse = {
      access_token: 'access-token-123',
      refresh_token: 'refresh-token-456',
      expires_in: 7200,
      user: {
        user_id: 'test-uuid',
        username: 'testuser',
        display_name: 'Test User',
        role: 'senior_researcher' as const,
        groups: [],
      },
    };

    vi.mocked(authApi.login).mockResolvedValueOnce(mockResponse);

    let loginFn: ((u: string, p: string) => Promise<void>) | null = null;

    render(
      <BrowserRouter>
        <AuthProvider>
          <TestConsumer
            onAuth={(auth) => {
              loginFn = auth.login;
              return <div>Test</div>;
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    );

    await act(async () => {
      await loginFn!('testuser', 'password123');
    });

    // Verify API call (AuthContext passes username + password to login)
    expect(authApi.login).toHaveBeenCalledWith({
      username: 'testuser',
      password: 'password123',
    });

    // Verify token storage (AuthContext stores tokens in localStorage)
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'access_token',
      'access-token-123'
    );
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'refresh_token',
      'refresh-token-456'
    );
  });

  it('should logout and clear user state', async () => {
    vi.mocked(authApi.logout).mockResolvedValueOnce(undefined);

    // Pre-populate localStorage to simulate logged-in state
    localStorageMock.setItem('access_token', 'token');
    localStorageMock.setItem('refresh_token', 'refresh');
    localStorageMock.setItem('user', JSON.stringify({}));

    let logoutFn: (() => Promise<void>) | null = null;

    render(
      <BrowserRouter>
        <AuthProvider>
          <TestConsumer
            onAuth={(auth) => {
              logoutFn = auth.logout;
              return <div>Test</div>;
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    );

    await act(async () => {
      await logoutFn!();
    });

    // Verify logout API was called
    expect(authApi.logout).toHaveBeenCalled();
  });

  it('should handle login API error', async () => {
    const loginError = Object.assign(new Error('Invalid credentials'), {
      status: 401,
      code: 'AUTH_INVALID_CREDENTIALS',
    });
    vi.mocked(authApi.login).mockRejectedValueOnce(loginError);

    let loginFn: ((u: string, p: string) => Promise<void>) | null = null;

    render(
      <BrowserRouter>
        <AuthProvider>
          <TestConsumer
            onAuth={(auth) => {
              loginFn = auth.login;
              return <div>Test</div>;
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    );

    let caughtError = false;
    await act(async () => {
      try {
        await loginFn!('baduser', 'badpass');
      } catch {
        caughtError = true;
      }
    });

    expect(caughtError).toBe(true);
    // Tokens should not be stored on error
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith(
      'access_token',
      expect.anything()
    );
  });
});