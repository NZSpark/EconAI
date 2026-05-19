import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Table,
  Button,
  Select,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Typography,
  Popconfirm,
  Empty,
  message,
  Progress,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  StopOutlined,
  RedoOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../hooks/useRequest';
import { listTasks, createTask, cancelTask, retryTask } from '../api/tasks';
import type { TaskListItem, CreateTaskRequest, TaskType, OutputFormat, LLMPreference } from '../api/types';

const { Title, Text } = Typography;

const taskTypeColorMap: Record<string, string> = {
  literature_review: 'blue',
  policy_draft: 'purple',
  policy_comparison: 'orange',
  tech_interpretation: 'cyan',
};

const taskTypeLabelMap: Record<string, string> = {
  literature_review: '文献综述',
  policy_draft: '政策草案',
  policy_comparison: '政策比较',
  tech_interpretation: '技术解读',
};

const taskStatusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'green',
  failed: 'red',
  cancelled: 'default',
};

const taskStatusLabelMap: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

export default function TaskList() {
  const { id: projectId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const loadTasks = useCallback(async () => {
    if (!projectId) throw new Error('No project ID');
    return listTasks(projectId, {
      page,
      page_size: pageSize,
      status: statusFilter,
      type: typeFilter,
    });
  }, [projectId, page, pageSize, statusFilter, typeFilter]);

  const { data, loading, error, run: refresh } = useRequest(loadTasks);

  const handleCreate = async (values: {
    type: TaskType;
    title: string;
    description: string;
    output_format: OutputFormat[];
    analysis_params: string;
  }) => {
    if (!projectId) return;
    setSubmitting(true);
    try {
      let analysisParams = {};
      try {
        analysisParams = values.analysis_params
          ? JSON.parse(values.analysis_params)
          : {};
      } catch {
        analysisParams = {};
      }

      const taskData: CreateTaskRequest = {
        type: values.type,
        title: values.title,
        description: values.description,
        kb_sources: {
          documents: [],
          include_institutional: false,
        },
        output_formats: values.output_format || ['md'],
        llm_preference: 'auto' as LLMPreference,
        analysis_params: analysisParams,
      };
      await createTask(projectId, taskData);
      message.success('任务创建成功');
      setCreateModalOpen(false);
      form.resetFields();
      refresh();
    } catch {
      message.error('任务创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (taskId: string) => {
    try {
      await cancelTask(taskId);
      message.success('任务已取消');
      refresh();
    } catch {
      message.error('取消失败');
    }
  };

  const handleRetry = async (taskId: string) => {
    try {
      await retryTask(taskId);
      message.success('已重新提交任务');
      refresh();
    } catch {
      message.error('重试失败');
    }
  };

  const columns: ColumnsType<TaskListItem> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (type: string) => (
        <Tag color={taskTypeColorMap[type] || 'default'}>
          {taskTypeLabelMap[type] || type}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={taskStatusColorMap[status] || 'default'}>
          {taskStatusLabelMap[status] || status}
        </Tag>
      ),
    },
    {
      title: '进度',
      key: 'progress',
      width: 200,
      render: (_: unknown, record: TaskListItem) => {
        if (!record.progress) {
          if (record.status === 'completed') return <Progress percent={100} size="small" />;
          if (record.status === 'failed') return <Text type="danger">执行失败</Text>;
          if (record.status === 'cancelled') return <Text type="secondary">已取消</Text>;
          return <Text type="secondary">等待中</Text>;
        }
        const pct = Math.round(
          (record.progress.step_index / record.progress.total_steps_estimate) * 100
        );
        return (
          <div>
            <Progress percent={pct} size="small" />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.progress.message}
            </Text>
          </div>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_: unknown, record: TaskListItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/projects/${projectId}/tasks/${record.task_id}`)}
          >
            查看
          </Button>
          {record.status === 'running' && (
            <Popconfirm
              title="确认取消"
              description="确定取消该任务？"
              onConfirm={() => handleCancel(record.task_id)}
              okText="确认"
              cancelText="返回"
            >
              <Button type="link" size="small" danger icon={<StopOutlined />}>
                取消
              </Button>
            </Popconfirm>
          )}
          {record.status === 'failed' && (
            <Button
              type="link"
              size="small"
              icon={<RedoOutlined />}
              onClick={() => handleRetry(record.task_id)}
            >
              重试
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={5} style={{ margin: 0 }}>
          任务列表
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            创建任务
          </Button>
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="状态筛选"
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v);
            setPage(1);
          }}
          allowClear
          style={{ width: 140 }}
          options={[
            { label: '全部', value: undefined },
            { label: '等待中', value: 'pending' },
            { label: '执行中', value: 'running' },
            { label: '已完成', value: 'completed' },
            { label: '失败', value: 'failed' },
            { label: '已取消', value: 'cancelled' },
          ]}
        />
        <Select
          placeholder="类型筛选"
          value={typeFilter}
          onChange={(v) => {
            setTypeFilter(v);
            setPage(1);
          }}
          allowClear
          style={{ width: 140 }}
          options={[
            { label: '全部', value: undefined },
            { label: '文献综述', value: 'literature_review' },
            { label: '政策草案', value: 'policy_draft' },
            { label: '政策比较', value: 'policy_comparison' },
            { label: '技术解读', value: 'tech_interpretation' },
          ]}
        />
      </Space>

      {error && (
        <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
          加载失败：{error.message || '未知错误'}
        </div>
      )}

      <Table<TaskListItem>
        columns={columns}
        dataSource={data?.items || []}
        rowKey="task_id"
        loading={loading}
        locale={{
          emptyText: <Empty description="暂无任务，点击按钮创建" />,
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total || 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个任务`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title="创建分析任务"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText="创建"
        cancelText="取消"
        confirmLoading={submitting}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="type"
            label="任务类型"
            rules={[{ required: true, message: '请选择任务类型' }]}
          >
            <Select
              placeholder="选择分析任务类型"
              options={[
                { label: '文献综述', value: 'literature_review' },
                { label: '政策草案', value: 'policy_draft' },
                { label: '政策比较', value: 'policy_comparison' },
                { label: '技术解读', value: 'tech_interpretation' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="title"
            label="任务标题"
            rules={[{ required: true, message: '请输入任务标题' }]}
          >
            <Input placeholder="例如：数字贸易规则对发展中国家的影响综述" />
          </Form.Item>
          <Form.Item name="description" label="任务描述">
            <Input.TextArea rows={3} placeholder="描述分析任务的目标和范围（可选）" />
          </Form.Item>
          <Form.Item
            name="output_format"
            label="输出格式"
            rules={[{ required: true, message: '请选择输出格式' }]}
            initialValue={['md']}
          >
            <Select
              mode="multiple"
              placeholder="选择输出格式"
              options={[
                { label: 'Markdown', value: 'md' },
                { label: 'Word (.docx)', value: 'docx' },
                { label: 'Excel (.xlsx)', value: 'xlsx' },
                { label: 'PowerPoint (.pptx)', value: 'pptx' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="analysis_params"
            label="分析参数（JSON）"
            tooltip="可选，JSON格式的分析参数，如专注领域、比较维度等"
          >
            <Input.TextArea
              rows={3}
              placeholder='{"focus_areas": ["经济影响", "政策建议"], "methodology_quality": true}'
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}