import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import AdminRoute from './components/AdminRoute';
import AppLayout from './components/Layout';
import Login from './pages/Login';
import ProjectList from './pages/ProjectList';
import ProjectDetail from './pages/ProjectDetail';
import KnowledgeBase from './pages/KnowledgeBase';
import TaskList from './pages/TaskList';
import TaskOutput from './pages/TaskOutput';
import UserManagement from './pages/Admin/UserManagement';
import GroupManagement from './pages/Admin/GroupManagement';
import AuditLogs from './pages/Admin/AuditLogs';
import Profile from './pages/Profile';
import NotFound from './pages/errors/NotFound';
import Forbidden from './pages/errors/Forbidden';
import ServerError from './pages/errors/ServerError';

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'Noto Sans CJK SC', sans-serif",
        },
      }}
    >
      <AntApp>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<Login />} />

              {/* Force password change (no layout, no navigation) */}
              <Route
                path="/force-password-change"
                element={
                  <PrivateRoute>
                    <Profile force />
                  </PrivateRoute>
                }
              />

              {/* Error pages (no layout) */}
              <Route path="/403" element={<Forbidden />} />
              <Route path="/500" element={<ServerError />} />

              {/* Protected routes */}
              <Route
                element={
                  <PrivateRoute>
                    <AppLayout />
                  </PrivateRoute>
                }
              >
                <Route path="/" element={<Navigate to="/projects" replace />} />

                {/* Projects */}
                <Route path="/projects" element={<ProjectList />} />
                <Route path="/projects/:id" element={<ProjectDetail />}>
                  <Route index element={<KnowledgeBase />} />
                  <Route path="knowledge-base" element={<KnowledgeBase />} />
                  <Route path="tasks" element={<TaskList />} />
                </Route>
                <Route
                  path="/projects/:id/tasks/:taskId"
                  element={<TaskOutput />}
                />

                {/* Profile */}
                <Route path="/profile" element={<Profile />} />

                {/* Admin routes */}
                <Route
                  path="/admin/users"
                  element={
                    <AdminRoute>
                      <UserManagement />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/groups"
                  element={
                    <AdminRoute>
                      <GroupManagement />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/audit-logs"
                  element={
                    <AdminRoute>
                      <AuditLogs />
                    </AdminRoute>
                  }
                />

                {/* 404 */}
                <Route path="*" element={<NotFound />} />
              </Route>

              {/* Redirect /admin to users */}
              <Route
                path="/admin"
                element={
                  <PrivateRoute>
                    <AdminRoute>
                      <Navigate to="/admin/users" replace />
                    </AdminRoute>
                  </PrivateRoute>
                }
              />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </AntApp>
    </ConfigProvider>
  );
}