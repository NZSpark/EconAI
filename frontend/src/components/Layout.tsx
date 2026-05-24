import { useState } from 'react';
import { Outlet, useNavigate, useLocation, Link } from 'react-router-dom';
import { Layout as AntLayout, Menu, Breadcrumb, Dropdown, Avatar, Space, theme } from 'antd';
import type { MenuProps } from 'antd';
import {
  ProjectOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  AuditOutlined,
  TeamOutlined,
  IdcardOutlined,
} from '@ant-design/icons';
import { useAuth } from '../hooks/useAuth';

const { Header, Sider, Content } = AntLayout;

const breadcrumbNameMap: Record<string, string> = {
  '/projects': '项目列表',
  '/projects/create': '创建项目',
  '/profile': '个人设置',
  '/admin': '管理',
  '/admin/users': '用户管理',
  '/admin/groups': '项目组管理',
  '/admin/audit-logs': '审计日志',
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const { token } = theme.useToken();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <IdcardOutlined />,
      label: '个人设置',
      onClick: () => navigate('/profile'),
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  // Determine selected menu key based on path
  let selectedKey = '/projects';
  if (location.pathname.startsWith('/admin/users')) {
    selectedKey = '/admin/users';
  } else if (location.pathname.startsWith('/admin/groups')) {
    selectedKey = '/admin/groups';
  } else if (location.pathname.startsWith('/admin/audit-logs')) {
    selectedKey = '/admin/audit-logs';
  } else if (location.pathname.startsWith('/admin')) {
    selectedKey = '/admin';
  } else if (location.pathname.startsWith('/projects')) {
    selectedKey = '/projects';
  }

  const menuItems: MenuProps['items'] = [
    {
      key: '/projects',
      icon: <ProjectOutlined />,
      label: <Link to="/projects">项目列表</Link>,
    },
  ];

  // Show admin menu for admin users
  if (user?.role === 'system_admin' || user?.role === 'project_admin') {
    const adminChildren: MenuProps['items'] = [
      {
        key: '/admin/users',
        icon: <UserOutlined />,
        label: <Link to="/admin/users">用户管理</Link>,
      },
      {
        key: '/admin/groups',
        icon: <TeamOutlined />,
        label: <Link to="/admin/groups">项目组管理</Link>,
      },
    ];

    if (user?.role === 'system_admin') {
      adminChildren.push({
        key: '/admin/audit-logs',
        icon: <AuditOutlined />,
        label: <Link to="/admin/audit-logs">审计日志</Link>,
      });
    }

    menuItems.push({
      key: '/admin',
      icon: <SettingOutlined />,
      label: <span>管理</span>,
      children: adminChildren,
    });
  }

  // Build breadcrumb items
  const pathParts = location.pathname.split('/').filter(Boolean);
  const breadcrumbItems: { title: React.ReactNode }[] = [
    { title: <Link to="/projects">首页</Link> },
  ];

  if (pathParts.length > 0) {
    let currentPath = '';
    for (const part of pathParts) {
      currentPath += `/${part}`;
      const label = breadcrumbNameMap[currentPath];
      if (label) {
        breadcrumbItems.push({ title: <span>{label}</span> });
      }
    }
  }

  // For project detail pages
  if (pathParts[0] === 'projects' && pathParts[1] && pathParts.length >= 2) {
    breadcrumbItems.push({ title: <span>项目详情</span> });
    if (pathParts[2] === 'knowledge-base') {
      breadcrumbItems.push({ title: <span>知识库</span> });
    } else if (pathParts[2] === 'tasks') {
      breadcrumbItems.push({ title: <span>任务</span> });
    }
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 10,
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: collapsed ? 16 : 18,
            fontWeight: 'bold',
            borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          {collapsed ? 'EAI' : 'EconAI'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          defaultOpenKeys={['/admin']}
          items={menuItems}
        />
      </Sider>

      <AntLayout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            padding: '0 24px',
            background: token.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
            position: 'sticky',
            top: 0,
            zIndex: 9,
          }}
        >
          <Breadcrumb items={breadcrumbItems} />
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} style={{ backgroundColor: token.colorPrimary }} />
              <span>{user?.display_name || user?.username || '用户'}</span>
            </Space>
          </Dropdown>
        </Header>

        <Content
          style={{
            margin: 16,
            padding: 24,
            background: token.colorBgContainer,
            borderRadius: 8,
            minHeight: 280,
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}