// ===== Auth Types =====

export interface LoginRequest {
  username: string;
  password: string;
  provider?: string;
}

export interface UserInfo {
  user_id: string;
  username: string;
  display_name: string;
  role: 'analyst' | 'senior_researcher' | 'project_admin' | 'system_admin';
  groups: UserGroup[];
  force_password_change?: boolean;
}

export interface UserGroup {
  group_id: string;
  name: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: UserInfo;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

// ===== Project Types =====

export type ProjectStatus = 'active' | 'archived';

export interface Project {
  project_id: string;
  name: string;
  description: string;
  group_id: string;
  group_name: string;
  status: ProjectStatus;
  document_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectRequest {
  name: string;
  description: string;
  group_id: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ===== Document Types =====

export type ParseStatus = 'pending' | 'parsing' | 'ready' | 'error' | 'deleted';
export type DocumentFormat = 'pdf' | 'docx' | 'doc' | 'xlsx' | 'xls' | 'csv' | 'pptx' | 'ppt' | 'md' | 'txt' | 'html' | 'eml';

export interface DocumentMetadata {
  title?: string;
  authors?: string;
  date?: string;
  source?: string;
  [key: string]: unknown;
}

export interface DocumentItem {
  document_id: string;
  original_name: string;
  format: DocumentFormat;
  size_bytes: number;
  page_count: number;
  parse_status: ParseStatus;
  metadata: DocumentMetadata;
  is_internal: boolean;
  chunk_count: number;
  parse_error?: string;
  storage_path?: string;
  created_at: string;
}

export interface UploadDocumentResponse {
  document_id: string;
  filename: string;
  format: string;
  size_bytes: number;
  parse_status: ParseStatus;
  created_at: string;
}

// ===== Task Types =====

export type TaskType = 'literature_review' | 'policy_draft' | 'policy_comparison' | 'tech_interpretation';
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type OutputFormat = 'md' | 'docx' | 'xlsx' | 'pptx';
export type LLMPreference = 'auto' | 'local' | 'cloud';

export interface KBSources {
  documents: string[];
  include_institutional: boolean;
}

export interface AnalysisParams {
  focus_areas?: string[];
  comparison_dimensions?: string[];
  methodology_quality?: boolean;
}

export interface CreateTaskRequest {
  type: TaskType;
  title: string;
  description?: string;
  kb_sources: KBSources;
  output_formats: OutputFormat[];
  llm_preference?: LLMPreference;
  analysis_params: AnalysisParams;
}

export interface CreateTaskResponse {
  task_id: string;
  status: TaskStatus;
  created_at: string;
}

export interface TaskProgress {
  step: string;
  step_index: number;
  total_steps_estimate: number;
  message: string;
  details?: Record<string, unknown>;
}

export interface TaskListItem {
  task_id: string;
  type: TaskType;
  title: string;
  status: TaskStatus;
  progress: TaskProgress | null;
  created_by: string;
  created_at: string;
}

export interface TaskDetail {
  task_id: string;
  project_id: string;
  type: TaskType;
  title: string;
  description: string;
  status: TaskStatus;
  progress: TaskProgress | null;
  params: CreateTaskRequest;
  llm_route: string;
  sensitivity: string;
  iteration_count: number;
  error_message: string | null;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface TaskStatusResponse {
  status: TaskStatus;
  progress: TaskProgress | null;
}

// ===== Search Types =====

export interface SearchFilters {
  document_ids?: string[];
  chunk_types?: string[];
  date_range?: { start: string; end: string };
}

export interface SearchRequest {
  query: string;
  top_k?: number;
  page?: number;
  page_size?: number;
  filters?: SearchFilters;
  search_mode?: string;
}

export interface SearchResultChunk {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  chunk_type: string;
  score: number;
  metadata: {
    page_start: number;
    page_end: number;
    section_title: string;
    paragraph_index?: number;
  };
  matched_terms: string[];
  highlighted_content: string;
}

export interface SearchResponse {
  results: SearchResultChunk[];
  total_hits: number;
  search_time_ms: number;
  page: number;
  page_size: number;
  pages: number;
}

// ===== Citation Types =====

export type CitationConfidence = 'direct' | 'fuzzy' | 'uncertain';

export interface MatchedChunk {
  chunk_id: string;
  document_id: string;
  page_start: number;
  page_end: number;
  excerpt: string;
  similarity: number;
}

export interface Citation {
  citation_id: string;
  ref_id: string;
  sentence: string;
  sentence_index: number;
  confidence: CitationConfidence;
  source: {
    document_id: string;
    document_title: string;
    page_start: number;
    page_end: number;
    excerpt: string;
  } | null;
  matched_chunks: MatchedChunk[];
  verified_at: string;
}

export interface CitationListResponse {
  citations: Citation[];
  summary: {
    total: number;
    direct: number;
    fuzzy: number;
    uncertain: number;
  };
}

// ===== Output Types =====

export interface TaskOutput {
  task_id: string;
  title: string;
  content: string;
  sections: OutputSection[];
  citations: CitationListResponse;
  created_at: string;
}

export interface OutputSection {
  title: string;
  level: number;
  content: string;
}

// ===== Admin Types =====

export interface AdminUser {
  user_id: string;
  username: string;
  email: string | null;
  display_name: string | null;
  role: string;
  auth_provider: string;
  is_active: boolean;
  force_password_change: boolean;
  created_at: string | null;
}

export interface CreateUserRequest {
  username: string;
  password: string;
  email: string;
  display_name: string;
  role: string;
  group_id?: string;   // existing group, required for project_admin
  group_name?: string;  // new group name, alternative to group_id
}

export interface AdminGroup {
  group_id: string;
  name: string;
  description: string;
  member_count: number;
  created_at: string;
}

export interface CreateGroupRequest {
  name: string;
  description: string;
}

export interface GroupMember {
  user_id: string;
  username: string;
  display_name: string | null;
  role: string;
}

export interface AuditLogEntry {
  audit_id: string;
  user_id: string;
  username?: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string;
  user_agent: string;
  created_at: string;
}

// ===== API Error =====

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ===== Password Management Types =====

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

export interface AdminResetPasswordRequest {
  new_password: string;
}