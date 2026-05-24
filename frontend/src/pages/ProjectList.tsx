import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Button,
  Input,
  Select,
  Space,
  Tag,
  Modal,
  Form,
  Typography,
  Popconfirm,
  Empty,
  message,
} from 'antd';
import { PlusOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../hooks/useRequest';
import { listProjects, createProject, archiveProject } from '../api/projects';
import { listGroups } from '../api/admin';
import type { Project, CreateProjectRequest, AdminGroup } from '../api/types';

const { Title } = Typography;

const statusColorMap: Record<string, string> = {
  active: 'green',
  archived: 'default',
};

const statusLabelMap: Record<string, string> = {
  active: '活跃',
  archived: '已归档',
};

export default function ProjectList() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [groups, setGroups] = useState<AdminGroup[]>([]);

  useEffect(() => {
    listGroups({ page: 1, page_size: 200 })
      .then((res) => {
        if (Array.isArray(res)) setGroups(res);
        else if (res?.items) setGroups(res.items);
      })
      .catch(() => {});
  }, []);

  const { data, loading, error, run: refresh } = useRequest(
    useCallback(async () => {
      return listProjects({
        page,
        page_size: pageSize,
        status: statusFilter,
        search: searchText || undefined,
      });
    }, [page, pageSize, statusFilter, searchText])
  );

  const handleCreate = async (values: CreateProjectRequest) => {
    try {
      await createProject(values);
      message.success('项目创建成功');
      setCreateModalOpen(false);
      form.resetFields();
      refresh();
    } catch {
      message.error('项目创建失败');
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await archiveProject(id);
      message.success('项目已归档');
      refresh();
    } catch {
      message.error('归档失败');
    }
  };

  const columns: ColumnsType<Project> = [
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Project) => (
        <a onClick={() => navigate(`/projects/${record.project_id}`)}>{text}</a>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '所属项目组',
      dataIndex: 'group_name',
      key: 'group_name',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {statusLabelMap[status] || status}
        </Tag>
      ),
    },
    {
      title: '文档数',
      dataIndex: 'document_count',
      key: 'document_count',
      width: 80,
      align: 'center',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: unknown, record: Project) => (
        <Space>
          <Button
            size="small"
            onClick={() => navigate(`/projects/${record.project_id}`)}
          >
            查看
          </Button>
          <Button
            size="small"
            onClick={() => navigate(`/projects/${record.project_id}/knowledge-base`)}
          >
            知识库
          </Button>
          {record.status === 'active' && (
            <Popconfirm
              title="确认归档"
              description="归档后项目将变为只读，确定归档？"
              onConfirm={() => handleArchive(record.project_id)}
              okText="确认"
              cancelText="取消"
            >
              <Button size="small" danger>
                归档
              </Button>
            </Popconfirm>
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
          marginBottom: 24,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          项目列表
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
            创建项目
          </Button>
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="搜索项目名称"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 240 }}
          onPressEnter={() => refresh()}
        />
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
            { label: '活跃', value: 'active' },
            { label: '已归档', value: 'archived' },
          ]}
        />
        <Button type="primary" onClick={() => refresh()}>
          搜索
        </Button>
      </Space>

      {error && (
        <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
          加载失败：{error.message || '未知错误'}
        </div>
      )}

      <Table<Project>
        columns={columns}
        dataSource={data?.items || []}
        rowKey="project_id"
        loading={loading}
        locale={{
          emptyText: <Empty description="暂无项目，点击按钮创建" />,
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total || 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个项目`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title="创建项目"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="例如：2024数字贸易政策研究" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
          >
            <Input.TextArea rows={3} placeholder="项目描述（可选）" />
          </Form.Item>
          <Form.Item
            name="group_id"
            label="所属项目组"
            rules={[{ required: true, message: '请选择项目组' }]}
          >
            <Select
              showSearch
              placeholder="搜索并选择项目组"
              optionFilterProp="label"
              options={groups.map((g) => ({
                label: g.name,
                value: g.group_id,
              }))}
              notFoundContent="暂无项目组，请联系管理员创建"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}