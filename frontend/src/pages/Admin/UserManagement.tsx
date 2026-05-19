import { useState, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Typography,
  Popconfirm,
  Empty,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../../hooks/useRequest';
import { listUsers, createUser, updateUser, disableUser } from '../../api/admin';
import type { AdminUser, CreateUserRequest } from '../../api/types';

const { Title } = Typography;

const roleColorMap: Record<string, string> = {
  analyst: 'default',
  senior_researcher: 'blue',
  project_admin: 'purple',
  system_admin: 'red',
};

const roleLabelMap: Record<string, string> = {
  analyst: '分析员',
  senior_researcher: '高级研究员',
  project_admin: '项目管理员',
  system_admin: '系统管理员',
};

export default function UserManagement() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [form] = Form.useForm();

  const loadUsers = useCallback(async () => {
    return listUsers({ page, page_size: pageSize });
  }, [page, pageSize]);

  const { data, loading, error, run: refresh } = useRequest(loadUsers);

  const handleCreateEdit = async (values: CreateUserRequest) => {
    try {
      if (editingUser) {
        await updateUser(editingUser.user_id, values);
        message.success('用户已更新');
      } else {
        await createUser(values);
        message.success('用户已创建');
      }
      setModalOpen(false);
      setEditingUser(null);
      form.resetFields();
      refresh();
    } catch {
      message.error(editingUser ? '更新失败' : '创建失败');
    }
  };

  const handleEdit = (user: AdminUser) => {
    setEditingUser(user);
    form.setFieldsValue({
      username: user.username,
      email: user.email,
      display_name: user.display_name,
      role: user.role,
    });
    setModalOpen(true);
  };

  const handleDisable = async (userId: string) => {
    try {
      await disableUser(userId);
      message.success('用户已停用');
      refresh();
    } catch {
      message.error('操作失败');
    }
  };

  const columns: ColumnsType<AdminUser> = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '显示名',
      dataIndex: 'display_name',
      key: 'display_name',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color={roleColorMap[role] || 'default'}>
          {roleLabelMap[role] || role}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>
          {status === 'active' ? '启用' : '禁用'}
        </Tag>
      ),
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
      width: 140,
      render: (_: unknown, record: AdminUser) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          {record.status === 'active' && (
            <Popconfirm
              title="确认停用"
              description="确定停用该用户？"
              onConfirm={() => handleDisable(record.user_id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                停用
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
          用户管理
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingUser(null);
              form.resetFields();
              setModalOpen(true);
            }}
          >
            创建用户
          </Button>
        </Space>
      </div>

      {error && (
        <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
          加载失败：{error.message || '未知错误'}
        </div>
      )}

      <Table<AdminUser>
        columns={columns}
        dataSource={data?.items || []}
        rowKey="user_id"
        loading={loading}
        locale={{
          emptyText: <Empty description="暂无用户" />,
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total || 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个用户`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title={editingUser ? '编辑用户' : '创建用户'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingUser(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText={editingUser ? '更新' : '创建'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={handleCreateEdit}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input disabled={!!editingUser} placeholder="登录用户名" />
          </Form.Item>
          {!editingUser && (
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password placeholder="初始密码" />
            </Form.Item>
          )}
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效邮箱' },
            ]}
          >
            <Input placeholder="user@example.com" />
          </Form.Item>
          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="用户显示名称" />
          </Form.Item>
          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select
              options={[
                { label: '分析员', value: 'analyst' },
                { label: '高级研究员', value: 'senior_researcher' },
                { label: '项目管理员', value: 'project_admin' },
                { label: '系统管理员', value: 'system_admin' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}