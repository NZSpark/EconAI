import { Spin, Alert, Empty, type AlertProps } from 'antd';

/**
 * Unified loading spinner with optional tip.
 */
export function Loading({ tip = '加载中...' }: { tip?: string }) {
  return (
    <div style={{ textAlign: 'center', padding: 64 }}>
      <Spin size="large" tip={tip} />
    </div>
  );
}

/**
 * Unified error display.
 */
export function ErrorDisplay({
  message = '加载失败',
  description,
  ...rest
}: {
  message?: string;
  description?: string;
} & Omit<AlertProps, 'message' | 'description'>) {
  return (
    <Alert
      type="error"
      message={message}
      description={description}
      showIcon
      style={{ marginBottom: 16 }}
      {...rest}
    />
  );
}

/**
 * Inline error text (used above tables).
 */
export function InlineError({ text }: { text?: string }) {
  return (
    <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
      加载失败：{text || '未知错误'}
    </div>
  );
}

/**
 * Unified empty state.
 */
export function EmptyState({ description }: { description: string }) {
  return <Empty description={description} />;
}
