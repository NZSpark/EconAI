import client from './client';
import type { LoginRequest, LoginResponse, RefreshResponse, ChangePasswordRequest } from './types';

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await client.post<LoginResponse>('/auth/login', {
    ...data,
    provider: data.provider || 'local',
  });
  return response.data;
}

export async function refreshToken(
  refreshToken: string
): Promise<RefreshResponse> {
  const response = await client.post<RefreshResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });
  return response.data;
}

export async function logout(): Promise<void> {
  try {
    await client.post('/auth/logout');
  } finally {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  }
}

export async function getCurrentUser() {
  const response = await client.get('/auth/me');
  return response.data;
}

export async function changePassword(data: ChangePasswordRequest): Promise<void> {
  await client.post('/auth/change-password', data);
}