import client from './client';
import type { SearchRequest, SearchResponse } from './types';

export async function searchProjectKB(
  projectId: string,
  data: SearchRequest
): Promise<SearchResponse> {
  const response = await client.post<SearchResponse>(
    `/projects/${projectId}/search`,
    data
  );
  return response.data;
}

export async function searchInstitutionalKB(
  data: SearchRequest
): Promise<SearchResponse> {
  const response = await client.post<SearchResponse>(
    '/institutional/search',
    data
  );
  return response.data;
}