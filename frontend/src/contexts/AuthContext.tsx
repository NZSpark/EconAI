import {
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react';
import { login as loginApi, logout as logoutApi } from '../api/auth';
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
  const isLoading = false;

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

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user,
      isAdmin,
      isLoading,
      login,
      logout,
    }),
    [user, isAdmin, isLoading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}