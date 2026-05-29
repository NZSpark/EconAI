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

/**
 * Download exported file via axios (with auth interceptor) and trigger browser download.
 * This avoids the AUTH_TOKEN_MISSING issue that occurs with window.open().
 */
export async function downloadExportFile(
  taskId: string,
  format: OutputFormat,
  filename?: string
): Promise<void> {
  const url = `/tasks/${taskId}/export`;
  const response = await client.get(url, {
    params: { format },
    responseType: 'blob',
  });

  // Extract filename from Content-Disposition header or use fallback
  let downloadFilename = filename || `output.${format}`;
  const disposition = response.headers['content-disposition'];
  if (disposition) {
    const match = disposition.match(/filename\*=UTF-8''(.+)/);
    if (match) {
      downloadFilename = decodeURIComponent(match[1]);
    } else {
      const simpleMatch = disposition.match(/filename="?([^"]+)"?/);
      if (simpleMatch) {
        downloadFilename = simpleMatch[1];
      }
    }
  }

  // Create object URL and trigger download
  const blob = response.data instanceof Blob
    ? response.data
    : new Blob([response.data]);
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = downloadFilename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(objectUrl);
}