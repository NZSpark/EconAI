import { useState, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  Typography,
  Empty,
  message,
  Popconfirm,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  UserAddOutlined,
  UserDeleteOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../../hooks/useRequest';
import {
  listGroups,
  createGroup,
  listGroupMembers,
  searchNonGroupMembers,
  addGroupMember,
  removeGroupMember,
} from '../../api/admin';
import type { AdminGroup, GroupMember, CreateGroupRequest } from '../../api/types';

const { Title } = Typography;

export default function GroupManagement() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<AdminGroup | null>(null);
  const [createForm] = Form.useForm();
  const [memberForm] = Form.useForm();

  // ---- Groups list ----
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
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '创建失败';
      message.error(`创建失败：${msg}`);
    }
  };

  // ---- Group members ----
  const [membersLoading, setMembersLoading] = useState(false);
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [userOptions, setUserOptions] = useState<{ value: string; label: string }[]>([]);

  const loadMembers = useCallback(
    async (group: AdminGroup) => {
      setMembersLoading(true);
      try {
        const list = await listGroupMembers(group.group_id);
        setMembers(list);
      } catch {
        setMembers([]);
      } finally {
        setMembersLoading(false);
      }
    },
    [],
  );

  const handleSearchUser = useCallback(
    async (query: string) => {
      if (!selectedGroup || !query) {
        setUserOptions([]);
        return;
      }
      try {
        const list = await searchNonGroupMembers(selectedGroup.group_id, query);
        setUserOptions(
          list.map((u) => ({
            value: u.user_id,
            label: u.display_name
              ? `${u.display_name} (${u.username})`
              : u.username,
          })),
        );
      } catch {
        setUserOptions([]);
      }
    },
    [selectedGroup],
  );

  const handleAddMember = async (values: { user_id: string }) => {
    if (!selectedGroup) return;
    try {
      await addGroupMember(selectedGroup.group_id, values.user_id);
      message.success('成员已添加');
      memberForm.resetFields();
      setUserOptions([]);
      await loadMembers(selectedGroup);
      refresh(); // refresh group list to update member_count
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '添加失败';
      message.error(`添加失败：${msg}`);
    }
  };

  const handleRemoveMember = async (userId: string) => {
    if (!selectedGroup) return;
    try {
      await removeGroupMember(selectedGroup.group_id, userId);
      message.success('成员已移除');
      await loadMembers(selectedGroup);
      refresh();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '移除失败';
      message.error(`移除失败：${msg}`);
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
            setMembers([]);
            setMemberModalOpen(true);
            loadMembers(record);
          }}
        >
          管理成员
        </Button>
      ),
    },
  ];

  const memberColumns: ColumnsType<GroupMember> = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 140,
    },
    {
      title: '显示名称',
      dataIndex: 'display_name',
      key: 'display_name',
      ellipsis: true,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 100,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, record: GroupMember) => (
        <Popconfirm
          title="确认移除"
          description={`确定要移除 ${record.display_name || record.username} 吗？`}
          onConfirm={() => handleRemoveMember(record.user_id)}
          okText="移除"
          cancelText="取消"
        >
          <Button type="link" danger size="small" icon={<UserDeleteOutlined />}>
            移除
          </Button>
        </Popconfirm>
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
          setMembers([]);
          setUserOptions([]);
          memberForm.resetFields();
        }}
        footer={null}
        width={600}
      >
        {/* Add member form */}
        <Form
          form={memberForm}
          layout="inline"
          onFinish={handleAddMember}
          style={{ marginBottom: 16 }}
        >
          <Form.Item
            name="user_id"
            rules={[{ required: true, message: '请选择用户' }]}
            style={{ flex: 1 }}
          >
            <Select
              showSearch
              placeholder="输入用户名或显示名称搜索"
              filterOption={false}
              onSearch={handleSearchUser}
              options={userOptions}
              notFoundContent={
                <Typography.Text type="secondary">输入关键字搜索</Typography.Text>
              }
              style={{ minWidth: 320 }}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<UserAddOutlined />}>
              添加成员
            </Button>
          </Form.Item>
        </Form>

        {/* Member list */}
        <Table<GroupMember>
          columns={memberColumns}
          dataSource={members}
          rowKey="user_id"
          loading={membersLoading}
          size="small"
          locale={{
            emptyText: <Empty description="暂无成员" />,
          }}
          pagination={false}
        />
      </Modal>
    </div>
  );
}