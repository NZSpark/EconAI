import { useParams, useLocation, Outlet } from 'react-router-dom';
import { Tabs, Typography, Spin, Empty, Alert, Descriptions, Tag, Card } from 'antd';
import { useRequest } from '../hooks/useRequest';
import { getProject } from '../api/projects';
const { Title } = Typography;

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();

  const { data: project, loading, error } = useRequest(
    async () => {
      if (!id) throw new Error('No project ID');
      return getProject(id);
    }
  );

  // Determine active tab from URL path
  let activeTab = 'info';
  if (location.pathname.includes('/knowledge-base')) {
    activeTab = 'knowledge-base';
  } else if (location.pathname.includes('/tasks')) {
    activeTab = 'tasks';
  }

  const handleTabChange = (key: string) => {
    if (key === 'info') {
      window.history.replaceState(null, '', `/projects/${id}`);
    } else if (key === 'knowledge-base') {
      window.history.replaceState(null, '', `/projects/${id}/knowledge-base`);
    } else if (key === 'tasks') {
      window.history.replaceState(null, '', `/projects/${id}/tasks`);
    }
    // Force a re-render by replacing path
    // For SPA routing, we'll handle this via the parent routing
    window.location.hash = '';
    if (key === 'info') {
      window.location.href = `/projects/${id}`;
    } else {
      window.location.href = `/projects/${id}/${key}`;
    }
  };

  const statusColorMap: Record<string, string> = {
    active: 'green',
    archived: 'default',
  };

  const statusLabelMap: Record<string, string> = {
    active: '活跃',
    archived: '已归档',
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="加载失败"
        description={error.message || '无法加载项目信息'}
        showIcon
      />
    );
  }

  if (!project) {
    return <Empty description="项目不存在" />;
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginBottom: 8 }}>
          {project.name}
        </Title>
        <Tag color={statusColorMap[project.status]}>
          {statusLabelMap[project.status]}
        </Tag>
      </div>

      <Card size="small" style={{ marginBottom: 24 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="描述">{project.description || '-'}</Descriptions.Item>
          <Descriptions.Item label="项目组">{project.group_name}</Descriptions.Item>
          <Descriptions.Item label="文档数量">{project.document_count}</Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {new Date(project.created_at).toLocaleString('zh-CN')}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'knowledge-base',
            label: '知识库',
            children: <Outlet context={{ projectId: id }} />,
          },
          {
            key: 'tasks',
            label: '任务',
            children: <Outlet context={{ projectId: id }} />,
          },
        ]}
      />
    </div>
  );
}