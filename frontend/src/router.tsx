import { Navigate, type RouteObject } from 'react-router-dom';
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

export const routes: RouteObject[] = [
  // Public routes
  { path: '/login', element: <Login /> },
  {
    path: '/force-password-change',
    element: (
      <PrivateRoute>
        <Profile force />
      </PrivateRoute>
    ),
  },

  // Error pages (no layout)
  { path: '/403', element: <Forbidden /> },
  { path: '/500', element: <ServerError /> },

  // Protected routes (with layout)
  {
    element: (
      <PrivateRoute>
        <AppLayout />
      </PrivateRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },

      // Projects
      { path: '/projects', element: <ProjectList /> },
      {
        path: '/projects/:id',
        element: <ProjectDetail />,
        children: [
          { index: true, element: <KnowledgeBase /> },
          { path: 'knowledge-base', element: <KnowledgeBase /> },
          { path: 'tasks', element: <TaskList /> },
        ],
      },
      { path: '/projects/:id/tasks/:taskId', element: <TaskOutput /> },

      // Profile
      { path: '/profile', element: <Profile /> },

      // Admin
      {
        path: '/admin/users',
        element: <AdminRoute><UserManagement /></AdminRoute>,
      },
      {
        path: '/admin/groups',
        element: <AdminRoute><GroupManagement /></AdminRoute>,
      },
      {
        path: '/admin/audit-logs',
        element: <AdminRoute><AuditLogs /></AdminRoute>,
      },

      // 404
      { path: '*', element: <NotFound /> },
    ],
  },

  // Redirect /admin → /admin/users
  {
    path: '/admin',
    element: (
      <PrivateRoute>
        <AdminRoute>
          <Navigate to="/admin/users" replace />
        </AdminRoute>
      </PrivateRoute>
    ),
  },
];
