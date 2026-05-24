import {
  useState,
  useCallback,
  useMemo,
  useEffect,
  type ReactNode,
} from 'react';
import { login as loginApi, logout as logoutApi, getCurrentUser, changePassword as changePasswordApi } from '../api/auth';
import type { UserInfo } from '../api/types';
import { AuthContext } from './auth-context';
import type { AuthContextValue } from './auth-context';

function loadUserFromStorage(): UserInfo | null {
  const storedUser = localStorage.getItem('user');
  const token = localStorage.getItem('access_token');
  if (storedUser && token) {
    try {
      return JSON.parse(storedUser);
    } catch {
      localStorage.removeItem('user');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(loadUserFromStorage);
  const [isLoading, setIsLoading] = useState(true);

  // Verify stored token on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    getCurrentUser()
      .then((userData) => {
        if (!cancelled) {
          setUser(userData);
          localStorage.setItem('user', JSON.stringify(userData));
        }
      })
      .catch(() => {
        if (!cancelled) {
          // Token invalid or expired — clear stored auth data
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user');
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const response = await loginApi({ username, password });
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    localStorage.setItem('user', JSON.stringify(response.user));
    setUser(response.user);
  }, []);

  const logout = useCallback(async () => {
    await logoutApi();
    setUser(null);
  }, []);

  const isAdmin =
    user?.role === 'system_admin' || user?.role === 'project_admin';

  const hasForcePasswordChange = user?.force_password_change ?? false;

  const changePassword = useCallback(
    async (oldPassword: string, newPassword: string) => {
      await changePasswordApi({ old_password: oldPassword, new_password: newPassword });
      // Refresh user data to get updated force_password_change flag
      try {
        const userData = await getCurrentUser();
        setUser(userData);
        localStorage.setItem('user', JSON.stringify(userData));
      } catch {
        // If /me fails, keep existing user data
      }
    },
    []
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user,
      isAdmin,
      isLoading,
      login,
      logout,
      changePassword,
      hasForcePasswordChange,
    }),
    [user, isAdmin, isLoading, login, logout, changePassword, hasForcePasswordChange]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}