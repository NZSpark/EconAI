import { useState, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Typography,
  Empty,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined, UserAddOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../../hooks/useRequest';
import { listGroups, createGroup, addGroupMember } from '../../api/admin';
import type { AdminGroup, CreateGroupRequest } from '../../api/types';

const { Title } = Typography;

export default function GroupManagement() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<AdminGroup | null>(null);
  const [createForm] = Form.useForm();
  const [memberForm] = Form.useForm();

  const loadGroups = useCallback(async () => {
    return listGroups({ page, page_size: pageSize });
  }, [page, pageSize]);

  const { data, loading, error, run: refresh } = useRequest(loadGroups);

  const handleCreate = async (values: CreateGroupRequest) => {
    try {
      await createGroup(values);
      message.success('项目组已创建');
      setCreateModalOpen(false);
      createForm.resetFields();
      refresh();
    } catch {
      message.error('创建失败');
    }
  };

  const handleAddMember = async (values: { user_id: string }) => {
    if (!selectedGroup) return;
    try {
      await addGroupMember(selectedGroup.group_id, values.user_id);
      message.success('成员已添加');
      setMemberModalOpen(false);
      memberForm.resetFields();
      refresh();
    } catch {
      message.error('添加失败');
    }
  };

  const columns: ColumnsType<AdminGroup> = [
    {
      title: '组名',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '成员数',
      dataIndex: 'member_count',
      key: 'member_count',
      width: 80,
      align: 'center',
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
      width: 120,
      render: (_: unknown, record: AdminGroup) => (
        <Button
          type="link"
          size="small"
          icon={<UserAddOutlined />}
          onClick={() => {
            setSelectedGroup(record);
            setMemberModalOpen(true);
          }}
        >
          管理成员
        </Button>
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
          项目组管理
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              createForm.resetFields();
              setCreateModalOpen(true);
            }}
          >
            创建项目组
          </Button>
        </Space>
      </div>

      {error && (
        <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
          加载失败：{error.message || '未知错误'}
        </div>
      )}

      <Table<AdminGroup>
        columns={columns}
        dataSource={data?.items || []}
        rowKey="group_id"
        loading={loading}
        locale={{
          emptyText: <Empty description="暂无项目组" />,
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total || 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个项目组`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      {/* Create Group Modal */}
      <Modal
        title="创建项目组"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          createForm.resetFields();
        }}
        onOk={() => createForm.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="name"
            label="组名"
            rules={[{ required: true, message: '请输入组名' }]}
          >
            <Input placeholder="例如：贸易政策研究组" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="项目组描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Manage Members Modal */}
      <Modal
        title={`管理成员 - ${selectedGroup?.name || ''}`}
        open={memberModalOpen}
        onCancel={() => {
          setMemberModalOpen(false);
          setSelectedGroup(null);
          memberForm.resetFields();
        }}
        footer={null}
      >
        <Form form={memberForm} layout="inline" onFinish={handleAddMember}>
          <Form.Item
            name="user_id"
            rules={[{ required: true, message: '请输入用户ID' }]}
          >
            <Input placeholder="用户ID (UUID)" style={{ width: 260 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<UserAddOutlined />}>
              添加
            </Button>
          </Form.Item>
        </Form>
        <div style={{ marginTop: 16 }}>
          <Typography.Text type="secondary">
            当前成员数：{selectedGroup?.member_count || 0}
          </Typography.Text>
          <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
            请输入要添加的用户 UUID 并在上方点击"添加"。成员列表将从 API 加载。
          </Typography.Paragraph>
        </div>
      </Modal>
    </div>
  );
}