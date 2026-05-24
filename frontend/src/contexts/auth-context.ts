import { createContext } from 'react';
import type { UserInfo } from '../api/types';

export interface AuthState {
  user: UserInfo | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isLoading: boolean;
}

export interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (oldPassword: string, newPassword: string) => Promise<void>;
  hasForcePasswordChange: boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);