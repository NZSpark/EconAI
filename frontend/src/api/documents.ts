import client from './client';
import type {
  DocumentItem,
  UploadDocumentResponse,
  PaginatedResponse,
} from './types';

export async function listDocuments(
  projectId: string,
  params?: {
    page?: number;
    page_size?: number;
    status?: string;
    format?: string;
  }
): Promise<PaginatedResponse<DocumentItem>> {
  const response = await client.get<PaginatedResponse<DocumentItem>>(
    `/projects/${projectId}/documents`,
    { params, timeout: 60000 }
  );
  return response.data;
}

export async function uploadDocument(
  projectId: string,
  file: File,
  isInternal?: boolean,
  metadata?: string,
  onProgress?: (percent: number) => void
): Promise<UploadDocumentResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (isInternal !== undefined) {
    formData.append('is_internal', String(isInternal));
  }
  if (metadata) {
    formData.append('metadata', metadata);
  }
  const response = await client.post<UploadDocumentResponse>(
    `/projects/${projectId}/documents`,
    formData,
    {
      // 不手动设置 Content-Type，让 Axios/browser 自动添加带 boundary 的头
      timeout: 120000,
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percent);
        }
      },
    }
  );
  return response.data;
}

export async function getDocument(
  projectId: string,
  documentId: string
): Promise<DocumentItem> {
  const response = await client.get<DocumentItem>(
    `/projects/${projectId}/documents/${documentId}`
  );
  return response.data;
}

export async function deleteDocument(
  projectId: string,
  documentId: string
): Promise<void> {
  await client.delete(`/projects/${projectId}/documents/${documentId}`);
}

export async function reindexDocument(
  projectId: string,
  documentId: string
): Promise<void> {
  await client.post(`/projects/${projectId}/documents/${documentId}/reindex`);
}

export interface DocumentContent {
  document_id: string;
  original_name: string;
  format: string;
  content_type: 'text' | 'image';
  text: string;
  page_count?: number;
  chunk_count?: number;
}

export async function getDocumentContent(
  projectId: string,
  documentId: string
): Promise<DocumentContent> {
  const response = await client.get<DocumentContent>(
    `/projects/${projectId}/documents/${documentId}/content`,
    { timeout: 60000 }
  );
  return response.data;
}

export function getDocumentDownloadUrl(
  projectId: string,
  documentId: string
): string {
  return `${client.defaults.baseURL}/projects/${projectId}/documents/${documentId}/download`;
}

/**
 * Download a document file via axios (with auth interceptor) and trigger browser download.
 * This avoids the AUTH_TOKEN_MISSING issue that occurs with window.open().
 */
export async function downloadDocumentFile(
  projectId: string,
  documentId: string,
  filename?: string
): Promise<void> {
  const url = `/projects/${projectId}/documents/${documentId}/download`;
  const response = await client.get(url, { responseType: 'blob' });

  // Extract filename from Content-Disposition header or use fallback
  let downloadFilename = filename || documentId;
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