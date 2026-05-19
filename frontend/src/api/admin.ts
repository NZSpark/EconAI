import client from './client';
import type {
  AdminUser,
  CreateUserRequest,
  AdminGroup,
  CreateGroupRequest,
  AuditLogEntry,
  PaginatedResponse,
} from './types';

// ===== User Management =====

export async function listUsers(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<PaginatedResponse<AdminUser>> {
  const response = await client.get<PaginatedResponse<AdminUser>>(
    '/admin/users',
    { params }
  );
  return response.data;
}

export async function createUser(data: CreateUserRequest): Promise<AdminUser> {
  const response = await client.post<AdminUser>('/admin/users', data);
  return response.data;
}

export async function updateUser(
  userId: string,
  data: Partial<CreateUserRequest>
): Promise<AdminUser> {
  const response = await client.put<AdminUser>(
    `/admin/users/${userId}`,
    data
  );
  return response.data;
}

export async function disableUser(userId: string): Promise<void> {
  await client.delete(`/admin/users/${userId}`);
}

// ===== Group Management =====

export async function listGroups(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<AdminGroup>> {
  const response = await client.get<PaginatedResponse<AdminGroup>>(
    '/admin/groups',
    { params }
  );
  return response.data;
}

export async function createGroup(
  data: CreateGroupRequest
): Promise<AdminGroup> {
  const response = await client.post<AdminGroup>('/admin/groups', data);
  return response.data;
}

export async function addGroupMember(
  groupId: string,
  userId: string
): Promise<void> {
  await client.post(`/admin/groups/${groupId}/members`, { user_id: userId });
}

export async function removeGroupMember(
  groupId: string,
  userId: string
): Promise<void> {
  await client.delete(`/admin/groups/${groupId}/members/${userId}`);
}

// ===== Audit Logs =====

export async function listAuditLogs(params?: {
  page?: number;
  page_size?: number;
  user_id?: string;
  action?: string;
  resource_type?: string;
  from?: string;
  to?: string;
}): Promise<PaginatedResponse<AuditLogEntry>> {
  const response = await client.get<PaginatedResponse<AuditLogEntry>>(
    '/admin/audit-logs',
    { params }
  );
  return response.data;
}