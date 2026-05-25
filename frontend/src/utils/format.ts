/** Shared formatting utilities. */

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/** 新西兰时区 */
const NZ_TIMEZONE = 'Pacific/Auckland';

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', { timeZone: NZ_TIMEZONE });
}
