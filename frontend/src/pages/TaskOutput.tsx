import { useState, useCallback, useMemo, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  Tag,
  Typography,
  Spin,
  Empty,
  Alert,
  Select,
  Drawer,
  Descriptions,
  message,
  Segmented,
} from 'antd';
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useRequest } from '../hooks/useRequest';
import { usePolling } from '../hooks/usePolling';
import { getTaskDetail, getTaskStatus, getTaskOutput as fetchTaskOutput, downloadExportFile, retryTask } from '../api/tasks';
import TaskProgress from '../components/TaskProgress';
import MarkdownPreview from '../components/MarkdownPreview';
import CitationBadge from '../components/CitationBadge';
import type { TaskDetail, Citation, OutputFormat } from '../api/types';
import { taskStatusColorMap, taskStatusLabelMap } from '../constants/labels';

const { Title, Text } = Typography;

const sensitivityLabelMap: Record<string, string> = { high: '高敏感度', low: '低敏感度' };
const sensitivityColorMap: Record<string, string> = { high: 'red', low: 'green' };
const llmRouteLabelMap: Record<string, string> = { local: '本地LLM', cloud: '云端LLM' };
const llmRouteColorMap: Record<string, string> = { local: 'orange', cloud: 'blue' };

export default function TaskOutput() {
  const { id: projectId, taskId } = useParams<{ id: string; taskId: string }>();
  const navigate = useNavigate();

  const [task, setTask] = useState<TaskDetail | null>(null);
  const [output, setOutput] = useState<{ content: string; citations: Citation[] } | null>(null);
  const [exportFormat, setExportFormat] = useState<OutputFormat>('docx');
  const [citationDrawerOpen, setCitationDrawerOpen] = useState(false);
  const [confidenceFilter, setConfidenceFilter] = useState<string>('all');
  const [viewMode, setViewMode] = useState<string>('preview');

  // Check if task is still running
  const isRunning = task?.status === 'running' || task?.status === 'pending';

  // Load task detail
  const { loading: taskLoading, error: taskError, run: loadTask } = useRequest(
    async () => {
      if (!taskId) throw new Error('No task ID');
      const detail = await getTaskDetail(taskId);
      setTask(detail);
      return detail;
    }
  );

  // Poll for task status if running
  usePolling(
    async () => {
      if (!taskId) return;
      try {
        const status = await getTaskStatus(taskId);
        setTask((prev) =>
          prev
            ? {
                ...prev,
                status: status.status,
                progress: status.progress,
              }
            : null
        );
        // If task completed or failed, stop polling and load output
        if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
          // Will be handled by the enabled condition
        }
      } catch {
        // Polling error is silent
      }
    },
    3000,
    isRunning
  );

  // Load output when task completes
  const [outputLoaded, setOutputLoaded] = useState(false);
  useEffect(() => {
    if (task?.status === 'completed' && !outputLoaded && taskId) {
      fetchTaskOutput(taskId)
        .then((res) => {
          setOutput({
            content: res.content,
            citations: res.citations?.citations || [],
          });
          setOutputLoaded(true);
        })
        .catch(() => {
          message.error('加载输出内容失败');
        });
    }
  }, [task?.status, taskId, outputLoaded]);

  // Build citation index map for markdown
  const citationMap = useMemo(() => {
    if (!output?.citations) return new Map();
    const map = new Map<number, { refId: string; confidence: string; sourceTitle?: string }>();
    output.citations.forEach((cit, idx) => {
      map.set(idx + 1, {
        refId: cit.ref_id,
        confidence: cit.confidence,
        sourceTitle: cit.source?.document_title,
      });
    });
    return map;
  }, [output]);

  // Filtered citations
  const filteredCitations = useMemo(() => {
    if (!output?.citations) return [];
    if (confidenceFilter === 'all') return output.citations;
    return output.citations.filter((c) => c.confidence === confidenceFilter);
  }, [output, confidenceFilter]);

  // Citation summary
  const citationSummary = useMemo(() => {
    if (!output?.citations) return { total: 0, direct: 0, fuzzy: 0, uncertain: 0 };
    return output.citations.reduce(
      (acc, c) => {
        acc.total++;
        acc[c.confidence]++;
        return acc;
      },
      { total: 0, direct: 0, fuzzy: 0, uncertain: 0 }
    );
  }, [output]);

  const handleExport = async () => {
    if (!taskId) return;
    try {
      const taskTitle = task?.title || 'output';
      await downloadExportFile(taskId, exportFormat, taskTitle);
    } catch {
      message.error('导出失败，请重试');
    }
  };

  const handleRetry = useCallback(async () => {
    if (!taskId) return;
    try {
      await retryTask(taskId);
      message.success('已重新提交任务');
      // Reset state to re-poll
      setOutputLoaded(false);
      setTask((prev) => prev ? { ...prev, status: 'pending' as const, error_message: null } : null);
    } catch {
      message.error('重试失败');
    }
  }, [taskId]);

  if (taskLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (taskError) {
    return (
      <Alert
        type="error"
        message="加载失败"
        description={taskError.message || '无法加载任务详情'}
        showIcon
      />
    );
  }

  if (!task) {
    return <Empty description="任务不存在" />;
  }

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space style={{ marginBottom: 8 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(`/projects/${projectId}/tasks`)}
          >
            返回任务列表
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => loadTask()}>
            刷新
          </Button>
        </Space>
        <Title level={4} style={{ marginTop: 8 }}>
          {task.title}
        </Title>
        <Space>
          <Tag color={taskStatusColorMap[task.status]}>
            {taskStatusLabelMap[task.status]}
          </Tag>
          {task.sensitivity && (
            <Tag color={sensitivityColorMap[task.sensitivity] || 'default'}>
              {sensitivityLabelMap[task.sensitivity] || task.sensitivity}
            </Tag>
          )}
          {task.llm_route && (
            <Tag color={llmRouteColorMap[task.llm_route] || 'default'}>
              {llmRouteLabelMap[task.llm_route] || task.llm_route}
            </Tag>
          )}
          {task.status === 'completed' && output && (
            <>
              <Tag color="blue">引用 {citationSummary.total}</Tag>
              <Tag color="green">直接 {citationSummary.direct}</Tag>
              <Tag color="gold">模糊 {citationSummary.fuzzy}</Tag>
              <Tag color="red">不确定 {citationSummary.uncertain}</Tag>
            </>
          )}
        </Space>
      </div>

      {/* Progress (if running/pending) */}
      {(isRunning || task.status === 'failed') && (
        <Card style={{ marginBottom: 24 }}>
          <TaskProgress progress={task.progress} status={task.status} />
          {task.status === 'failed' && task.error_message && (
            <Alert
              type="error"
              message="执行错误"
              description={task.error_message}
              style={{ marginTop: 12 }}
              showIcon
              action={
                <Button size="small" danger onClick={handleRetry}>
                  重试
                </Button>
              }
            />
          )}
        </Card>
      )}

      {/* Output content */}
      {task.status === 'completed' && output && (
        <div style={{ display: 'flex', gap: 16 }}>
          {/* Main content area */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <Card
              extra={
                <Space>
                  <Segmented
                    value={viewMode}
                    onChange={(val) => setViewMode(val as string)}
                    options={[
                      { label: '预览', value: 'preview' },
                      { label: '原文', value: 'raw' },
                    ]}
                  />
                  <Button
                    type="primary"
                    icon={<DownloadOutlined />}
                    onClick={handleExport}
                  >
                    导出
                  </Button>
                  <Select
                    value={exportFormat}
                    onChange={(v) => setExportFormat(v as OutputFormat)}
                    style={{ width: 120 }}
                    options={[
                      { label: 'Markdown', value: 'md' },
                      { label: 'Word (.docx)', value: 'docx' },
                      { label: 'Excel (.xlsx)', value: 'xlsx' },
                      { label: 'PPT (.pptx)', value: 'pptx' },
                    ]}
                  />
                  <Button
                    onClick={() => setCitationDrawerOpen(true)}
                  >
                    引用列表 ({citationSummary.total})
                  </Button>
                </Space>
              }
            >
              {viewMode === 'preview' ? (
                <div
                  style={{
                    maxHeight: '70vh',
                    overflowY: 'auto',
                    padding: 16,
                    background: '#fff',
                  }}
                >
                  <MarkdownPreview
                    content={output.content}
                    citationMap={citationMap}
                    onCitationClick={() => {
                      setConfidenceFilter('all');
                      setCitationDrawerOpen(true);
                    }}
                  />
                </div>
              ) : (
                <pre
                  style={{
                    maxHeight: '70vh',
                    overflowY: 'auto',
                    padding: 16,
                    background: '#f5f5f5',
                    borderRadius: 4,
                    fontSize: 13,
                    whiteSpace: 'pre-wrap',
                    wordWrap: 'break-word',
                  }}
                >
                  {output.content}
                </pre>
              )}
            </Card>
          </div>
        </div>
      )}

      {/* Citation Drawer */}
      <Drawer
        title={
          <Space>
            <span>引用列表 ({filteredCitations.length})</span>
            <Select
              value={confidenceFilter}
              onChange={(v) => setConfidenceFilter(v)}
              size="small"
              style={{ width: 120 }}
              options={[
                { label: '全部', value: 'all' },
                { label: '直接引用', value: 'direct' },
                { label: '模糊引用', value: 'fuzzy' },
                { label: '不确定', value: 'uncertain' },
              ]}
            />
          </Space>
        }
        open={citationDrawerOpen}
        onClose={() => setCitationDrawerOpen(false)}
        width={480}
      >
        {filteredCitations.length === 0 && (
          <Empty description="无匹配的引用" />
        )}
        {filteredCitations.map((citation: Citation, idx: number) => (
          <Card
            key={citation.ref_id}
            size="small"
            style={{ marginBottom: 12 }}
            title={
              <Space>
                <CitationBadge
                  index={idx + 1}
                  confidence={citation.confidence}
                />
                <Text ellipsis style={{ maxWidth: 280 }}>
                  {citation.source?.document_title || citation.ref_id}
                </Text>
              </Space>
            }
          >
            <Descriptions column={1} size="small">
              <Descriptions.Item label="出处">
                {citation.source
                  ? `第 ${citation.source.page_start}-${citation.source.page_end} 页`
                  : '未找到来源'}
              </Descriptions.Item>
              <Descriptions.Item label="原文句子">
                <Text style={{ fontSize: '0.85em' }}>{citation.sentence}</Text>
              </Descriptions.Item>
              {citation.source?.excerpt && (
                <Descriptions.Item label="来源摘录">
                  <Text
                    type="secondary"
                    style={{ fontSize: '0.85em' }}
                  >
                    {citation.source.excerpt}
                  </Text>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="置信度">
                <CitationBadge confidence={citation.confidence} index={idx + 1} />
              </Descriptions.Item>
            </Descriptions>
          </Card>
        ))}
      </Drawer>
    </div>
  );
}