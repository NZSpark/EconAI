import client from './client';
import type {
  CreateTaskRequest,
  CreateTaskResponse,
  TaskListItem,
  TaskDetail,
  TaskStatusResponse,
  TaskOutput,
  PaginatedResponse,
  OutputFormat,
} from './types';

export async function listTasks(
  projectId: string,
  params?: {
    page?: number;
    page_size?: number;
    status?: string;
    type?: string;
  }
): Promise<PaginatedResponse<TaskListItem>> {
  const response = await client.get<PaginatedResponse<TaskListItem>>(
    `/projects/${projectId}/tasks`,
    { params }
  );
  return response.data;
}

export async function createTask(
  projectId: string,
  data: CreateTaskRequest
): Promise<CreateTaskResponse> {
  const response = await client.post<CreateTaskResponse>(
    `/projects/${projectId}/tasks`,
    data
  );
  return response.data;
}

export async function getTaskDetail(taskId: string): Promise<TaskDetail> {
  const response = await client.get<TaskDetail>(`/tasks/${taskId}`);
  return response.data;
}

export async function getTaskStatus(
  taskId: string
): Promise<TaskStatusResponse> {
  const response = await client.get<TaskStatusResponse>(
    `/tasks/${taskId}/status`
  );
  return response.data;
}

export async function getTaskOutput(taskId: string): Promise<TaskOutput> {
  const response = await client.get<TaskOutput>(`/tasks/${taskId}/output`);
  return response.data;
}

export async function cancelTask(taskId: string): Promise<void> {
  await client.post(`/tasks/${taskId}/cancel`);
}

export async function retryTask(taskId: string): Promise<void> {
  await client.post(`/tasks/${taskId}/retry`);
}

export function getExportUrl(taskId: string, format: OutputFormat): string {
  const baseUrl = '/api';
  return `${baseUrl}/tasks/${taskId}/export?format=${format}`;
}