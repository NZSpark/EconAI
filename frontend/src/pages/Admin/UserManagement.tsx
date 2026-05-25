import { useState, useCallback, useMemo, useEffect } from 'react';
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
  Radio,
} from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, KeyOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../../hooks/useRequest';
import { listUsers, createUser, updateUser, disableUser, resetUserPassword, listGroups } from '../../api/admin';
import type { AdminUser, AdminGroup, CreateUserRequest } from '../../api/types';
import { useAuth } from '../../hooks/useAuth';
import { roleColorMap, roleLabelMap } from '../../constants/labels';

const { Title } = Typography;

export default function UserManagement() {
  const { user: currentUser } = useAuth();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [form] = Form.useForm();
  const [resetPwdOpen, setResetPwdOpen] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetForm] = Form.useForm();

  // Group management for project_admin
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [groupMode, setGroupMode] = useState<'select' | 'create'>('select');

  useEffect(() => {
    listGroups({ page: 1, page_size: 200 }).then((res) => {
      if (Array.isArray(res)) {
        setGroups(res);
      } else if (res?.items) {
        setGroups(res.items);
      }
    }).catch(() => {});
  }, []);

  // Only system_admin can assign the system_admin role
  const roleOptions = useMemo(() => {
    const options = [
      { label: '分析员', value: 'analyst' },
      { label: '高级研究员', value: 'senior_researcher' },
      { label: '项目管理员', value: 'project_admin' },
    ];
    if (currentUser?.role === 'system_admin') {
      options.push({ label: '系统管理员', value: 'system_admin' });
    }
    return options;
  }, [currentUser?.role]);

  const loadUsers = useCallback(async () => {
    return listUsers({ page, page_size: pageSize });
  }, [page, pageSize]);

  const { data, loading, error, run: refresh } = useRequest(loadUsers);

  const handleCreateEdit = async (values: any) => {
    try {
      if (editingUser) {
        // Editing: strip group fields (group binding only at creation)
        const { group_id, group_name, ...updateValues } = values;
        await updateUser(editingUser.user_id, updateValues);
        message.success('用户已更新');
      } else {
        // Creating: map group fields based on mode
        const payload: CreateUserRequest = { ...values };
        if (payload.role === 'project_admin') {
          if (groupMode === 'select') {
            delete payload.group_name;
          } else {
            delete payload.group_id;
          }
        } else {
          delete payload.group_id;
          delete payload.group_name;
        }
        await createUser(payload);
        message.success('用户已创建');
      }
      setModalOpen(false);
      setEditingUser(null);
      setGroupMode('select');
      form.resetFields();
      refresh();
    } catch (err: any) {
      // Handle backend error codes with user-friendly Chinese messages
      const errorCodeMap: Record<string, string> = {
        USER_ALREADY_EXISTS: '用户名已存在，请更换用户名',
        MEMBER_ALREADY_EXISTS: '用户已是该组成员',
        GROUP_NOT_FOUND: '所选项目组不存在',
      };
      if (err?.code && errorCodeMap[err.code]) {
        message.error(errorCodeMap[err.code]);
      } else if (err?.message) {
        message.error(err.message);
      // Handle raw Pydantic 422 validation errors (not transformed by interceptor)
      } else if (err?.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (Array.isArray(detail)) {
          const msgs = detail.map((d: any) => d.msg).join('；');
          message.error(msgs);
        } else if (typeof detail === 'string') {
          message.error(detail);
        } else {
          message.error(editingUser ? '更新失败' : '创建失败');
        }
      } else {
        message.error(editingUser ? '更新失败' : '创建失败');
      }
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

  const handleResetPassword = async (values: { new_password: string }) => {
    if (!resetTarget) return;
    try {
      await resetUserPassword(resetTarget.user_id, { new_password: values.new_password });
      message.success('密码已重置，用户下次登录时需修改密码');
      setResetPwdOpen(false);
      setResetTarget(null);
      resetForm.resetFields();
      refresh();
    } catch (err: any) {
      if (err?.code === 'AUTH_LDAP_PASSWORD') {
        message.error('无法重置LDAP用户的密码');
      } else if (err?.message) {
        message.error(err.message);
      } else {
        message.error('重置失败');
      }
    }
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
      key: 'status',
      width: 100,
      render: (_: unknown, record: AdminUser) => (
        <Space size={4}>
          <Tag color={record.is_active ? 'green' : 'default'}>
            {record.is_active ? '启用' : '禁用'}
          </Tag>
          {record.force_password_change && record.is_active && (
            <Tag color="orange" style={{ fontSize: 11 }}>待改密</Tag>
          )}
        </Space>
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
      width: 200,
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
          {record.is_active && (
            <Button
              type="link"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => {
                setResetTarget(record);
                resetForm.resetFields();
                setResetPwdOpen(true);
              }}
            >
              重置密码
            </Button>
          )}
          {record.is_active && (
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
              setGroupMode('select');
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
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少8位' },
              ]}
            >
              <Input.Password placeholder="初始密码（至少8位）" />
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
            <Select options={roleOptions} onChange={(val) => {
              if (val !== 'project_admin') {
                form.setFieldsValue({ group_id: undefined, group_name: undefined });
              }
            }} />
          </Form.Item>

          {/* Group binding — visible only when creating a project_admin */}
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.role !== cur.role}>
            {({ getFieldValue }) => {
              const role = getFieldValue('role');
              if (role !== 'project_admin' || editingUser) return null;
              return (
                <>
                  <Form.Item label="项目组绑定方式" style={{ marginBottom: 8 }}>
                    <Radio.Group
                      value={groupMode}
                      onChange={(e) => {
                        setGroupMode(e.target.value);
                        form.setFieldsValue({ group_id: undefined, group_name: undefined });
                      }}
                    >
                      <Radio.Button value="select">选择已有项目组</Radio.Button>
                      <Radio.Button value="create">创建新项目组</Radio.Button>
                    </Radio.Group>
                  </Form.Item>
                  {groupMode === 'select' ? (
                    <Form.Item
                      name="group_id"
                      label="项目组"
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
                        notFoundContent="暂无项目组"
                      />
                    </Form.Item>
                  ) : (
                    <Form.Item
                      name="group_name"
                      label="新项目组名称"
                      rules={[
                        { required: true, message: '请输入项目组名称' },
                        { max: 256, message: '名称最多256字符' },
                      ]}
                    >
                      <Input placeholder="输入新项目组名称" />
                    </Form.Item>
                  )}
                </>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码 - ${resetTarget?.username || ''}`}
        open={resetPwdOpen}
        onCancel={() => {
          setResetPwdOpen(false);
          setResetTarget(null);
          resetForm.resetFields();
        }}
        onOk={() => resetForm.submit()}
        okText="确认重置"
        cancelText="取消"
      >
        <div
          style={{
            background: '#fff7e6',
            border: '1px solid #ffd591',
            borderRadius: 6,
            padding: '10px 16px',
            marginBottom: 16,
          }}
        >
          <Typography.Text style={{ color: '#d46b08', fontSize: 13 }}>
            重置后该用户下次登录时必须修改密码。
          </Typography.Text>
        </div>
        <Form form={resetForm} layout="vertical" onFinish={handleResetPassword}>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 8, message: '密码至少8位' },
            ]}
          >
            <Input.Password placeholder="输入新密码（至少8位）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}