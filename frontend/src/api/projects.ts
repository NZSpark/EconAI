import client from './client';
import type {
  Project,
  CreateProjectRequest,
  PaginatedResponse,
} from './types';

export async function listProjects(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}): Promise<PaginatedResponse<Project>> {
  const response = await client.get<PaginatedResponse<Project>>('/projects', {
    params,
  });
  return response.data;
}

export async function getProject(id: string): Promise<Project> {
  const response = await client.get<Project>(`/projects/${id}`);
  return response.data;
}

export async function createProject(data: CreateProjectRequest): Promise<Project> {
  const response = await client.post<Project>('/projects', data);
  return response.data;
}

export async function updateProject(
  id: string,
  data: Partial<CreateProjectRequest>
): Promise<Project> {
  const response = await client.put<Project>(`/projects/${id}`, data);
  return response.data;
}

export async function archiveProject(id: string): Promise<void> {
  await client.delete(`/projects/${id}`);
}