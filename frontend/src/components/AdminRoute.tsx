import { type ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Result, Button } from 'antd';

interface AdminRouteProps {
  children: ReactNode;
}

export default function AdminRoute({ children }: AdminRouteProps) {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (user?.role !== 'system_admin' && user?.role !== 'project_admin') {
    return (
      <Result
        status="403"
        title="403"
        subTitle="您没有访问该页面的权限"
        extra={
          <Button type="primary" href="/projects">
            返回项目列表
          </Button>
        }
      />
    );
  }

  return <>{children}</>;
}