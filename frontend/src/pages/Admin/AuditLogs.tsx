import { useState, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Select,
  Input,
  DatePicker,
  Typography,
  Empty,
  Tag,
} from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../../hooks/useRequest';
import { listAuditLogs } from '../../api/admin';
import type { AuditLogEntry } from '../../api/types';
import { auditActionColorMap } from '../../constants/labels';

const { Title } = Typography;

export default function AuditLogs() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [userIdFilter, setUserIdFilter] = useState('');
  const [actionFilter, setActionFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);

  const loadLogs = useCallback(async () => {
    const params: Record<string, unknown> = { page, page_size: pageSize };
    if (userIdFilter) params.user_id = userIdFilter;
    if (actionFilter) params.action = actionFilter;
    if (dateRange) {
      params.from_date = dateRange[0];
      params.to_date = dateRange[1];
    }
    return listAuditLogs(params as never);
  }, [page, pageSize, userIdFilter, actionFilter, dateRange]);

  const { data, loading, error, run: refresh } = useRequest(loadLogs);

  const columns: ColumnsType<AuditLogEntry> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      width: 120,
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 140,
      render: (action: string) => (
        <Tag color={auditActionColorMap[action] || 'default'}>{action}</Tag>
      ),
    },
    {
      title: '资源类型',
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 100,
    },
    {
      title: '资源ID',
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 200,
      ellipsis: true,
      render: (text: string | null) =>
        text ? (
          <Typography.Text copyable={{ text }} style={{ fontSize: 12 }}>
            {text.substring(0, 8)}...
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
    },
    {
      title: 'IP地址',
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 130,
    },
    {
      title: '详情',
      dataIndex: 'details',
      key: 'details',
      ellipsis: true,
      render: (details: Record<string, unknown>) => (
        <Typography.Text style={{ fontSize: 12 }}>
          {JSON.stringify(details).substring(0, 60)}
        </Typography.Text>
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
          审计日志
        </Title>
        <Button icon={<ReloadOutlined />} onClick={refresh}>
          刷新
        </Button>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="用户ID"
          prefix={<SearchOutlined />}
          value={userIdFilter}
          onChange={(e) => setUserIdFilter(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
        <Select
          placeholder="操作类型"
          value={actionFilter}
          onChange={(v) => {
            setActionFilter(v);
            setPage(1);
          }}
          allowClear
          style={{ width: 160 }}
          options={[
            { label: '全部', value: undefined },
            { label: '登录', value: 'login' },
            { label: '登出', value: 'logout' },
            { label: '创建项目', value: 'create_project' },
            { label: '归档项目', value: 'archive_project' },
            { label: '上传文档', value: 'upload_document' },
            { label: '删除文档', value: 'delete_document' },
            { label: '创建任务', value: 'create_task' },
          ]}
        />
        <DatePicker.RangePicker
          onChange={(dates) => {
            if (dates && dates[0] && dates[1]) {
              setDateRange([
                dates[0].toISOString(),
                dates[1].toISOString(),
              ]);
            } else {
              setDateRange(null);
            }
          }}
        />
        <Button type="primary" onClick={() => refresh()}>
          查询
        </Button>
      </Space>

      {error && (
        <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
          加载失败：{error.message || '未知错误'}
        </div>
      )}

      <Table<AuditLogEntry>
        columns={columns}
        dataSource={data?.items || []}
        rowKey="audit_id"
        loading={loading}
        locale={{
          emptyText: <Empty description="暂无审计日志" />,
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total || 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条记录`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />
    </div>
  );
}