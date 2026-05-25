/**
 * Shared label/color maps for the entire frontend.
 * All page-level color/label maps are consolidated here to avoid duplication.
 */

// ── Project status ──
export const projectStatusColorMap: Record<string, string> = {
  active: 'green',
  archived: 'default',
};

export const projectStatusLabelMap: Record<string, string> = {
  active: '活跃',
  archived: '已归档',
};

// ── Task type ──
export const taskTypeColorMap: Record<string, string> = {
  literature_review: 'blue',
  policy_draft: 'purple',
  policy_comparison: 'orange',
  tech_interpretation: 'cyan',
};

export const taskTypeLabelMap: Record<string, string> = {
  literature_review: '文献综述',
  policy_draft: '政策草案',
  policy_comparison: '政策比较',
  tech_interpretation: '技术解读',
};

// ── Task status ──
export const taskStatusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'green',
  failed: 'red',
  cancelled: 'default',
};

export const taskStatusLabelMap: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

// ── Parse status (document) ──
export const parseStatusColorMap: Record<string, string> = {
  pending: 'default',
  parsing: 'processing',
  ready: 'green',
  error: 'red',
  deleted: 'default',
};

export const parseStatusLabelMap: Record<string, string> = {
  pending: '等待中',
  parsing: '解析中',
  ready: '就绪',
  error: '解析失败',
  deleted: '已删除',
};

// ── Document format colors ──
export const formatColorMap: Record<string, string> = {
  pdf: 'red',
  docx: 'blue',
  doc: 'blue',
  xlsx: 'green',
  xls: 'green',
  csv: 'green',
  pptx: 'orange',
  ppt: 'orange',
  md: 'purple',
  txt: 'default',
  html: 'cyan',
  eml: 'geekblue',
};

// ── User role ──
export const roleColorMap: Record<string, string> = {
  analyst: 'default',
  senior_researcher: 'blue',
  project_admin: 'purple',
  system_admin: 'red',
};

export const roleLabelMap: Record<string, string> = {
  analyst: '分析员',
  senior_researcher: '高级研究员',
  project_admin: '项目管理员',
  system_admin: '系统管理员',
};

// ── Audit action ──
export const auditActionColorMap: Record<string, string> = {
  create_task: 'blue',
  upload_document: 'green',
  delete_document: 'red',
  login: 'purple',
  logout: 'default',
  create_project: 'cyan',
  archive_project: 'orange',
};
