# CLAUDE.md — frontend

## Role

Single-page application (React 19 + TypeScript 5 + Vite 8). Provides full UI for project management, document upload/knowledge base, task creation/tracking, output viewing with citation badges, and admin panel (users, groups, audit logs).

## Directory structure

```
frontend/
├── package.json
├── vite.config.ts              # Vite proxy → localhost:8000 (API gateway)
├── vitest.config.ts            # Mock tests (jsdom)
├── vitest.config.integrated.ts # Integration tests (node)
├── tsconfig.json
├── README.md
├── src/
│   ├── App.tsx                 # ConfigProvider + BrowserRouter entry
│   ├── main.tsx                # ReactDOM entry
│   ├── router.tsx              # Route definitions (separated from App)
│   ├── contexts/
│   │   ├── auth-context.ts     # AuthContext type definition
│   │   └── AuthContext.tsx     # JWT storage, auto-refresh, 401 retry
│   ├── api/
│   │   ├── client.ts           # Axios: JWT injection, token refresh, error handling
│   │   ├── types.ts            # TypeScript type definitions (all API types)
│   │   ├── auth.ts             # Login / logout / refresh / me / change-password
│   │   ├── projects.ts         # Project CRUD
│   │   ├── documents.ts        # Document upload, list, delete, reindex, content
│   │   ├── tasks.ts            # Task create, poll, cancel, retry, export
│   │   ├── search.ts           # KB hybrid search
│   │   └── admin.ts            # User / group / audit management
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── ProjectList.tsx     # Project table + create modal
│   │   ├── ProjectDetail.tsx   # Tabs: KB, tasks
│   │   ├── KnowledgeBase.tsx   # Document list, upload, KB search, content preview
│   │   ├── TaskList.tsx        # Task table + create modal + status filter
│   │   ├── TaskOutput.tsx      # Markdown preview + citation drawer + export
│   │   ├── Profile.tsx         # User info + change password
│   │   ├── Admin/
│   │   │   ├── UserManagement.tsx
│   │   │   ├── GroupManagement.tsx
│   │   │   └── AuditLogs.tsx
│   │   └── errors/
│   │       ├── NotFound.tsx
│   │       ├── Forbidden.tsx
│   │       └── ServerError.tsx
│   ├── components/
│   │   ├── Layout.tsx          # Sider + Header + Outlet
│   │   ├── PrivateRoute.tsx    # Auth guard
│   │   ├── AdminRoute.tsx      # Admin role guard
│   │   ├── ErrorBoundary.tsx   # React error boundary
│   │   ├── LoadingError.tsx    # Shared Loading / ErrorDisplay / InlineError / EmptyState
│   │   ├── MarkdownPreview.tsx # react-markdown with citation links
│   │   ├── CitationBadge.tsx   # Confidence badge (green/yellow/red)
│   │   ├── CitationPopover.tsx # Citation detail popover
│   │   ├── DocumentUpload.tsx  # Drag-drop upload
│   │   └── TaskProgress.tsx    # Progress Steps
│   ├── constants/
│   │   ├── citations.ts        # Citation confidence color/label maps
│   │   └── labels.ts           # All shared color/label maps (statuses, types, roles, etc.)
│   ├── utils/
│   │   └── format.ts           # formatFileSize, formatDate
│   └── hooks/
│       ├── useAuth.ts          # AuthContext consumer hook
│       ├── usePolling.ts       # Generic setInterval polling
│       └── useRequest.ts       # Async request wrapper (loading/error/data)
```

## Route tree

```
/login                           → Login
/force-password-change           → Profile (force mode)
/403                             → Forbidden
/500                             → ServerError
/                                → Redirect → /projects
/projects                        → ProjectList
/projects/:id                    → ProjectDetail
  /knowledge-base                → KnowledgeBase
  /tasks                         → TaskList
/projects/:id/tasks/:taskId      → TaskOutput
/profile                         → Profile
/admin/users                     → UserManagement
/admin/groups                    → GroupManagement
/admin/audit-logs                → AuditLogs
/admin                           → Redirect → /admin/users
*                                → NotFound
```

## Tech stack

| Layer | Library |
|-------|---------|
| Framework | React 19 + TypeScript 5 (strict) |
| Build | Vite 8 |
| UI | Ant Design 6 + @ant-design/icons |
| Routing | React Router 7 |
| HTTP | Axios |
| Markdown | react-markdown |
| Testing | Vitest 4 + Testing Library + jsdom |

## Run / test

```bash
npm install
npm run dev                # Opens :5173, proxies /api → :8000
npm test                   # Vitest (mock tests)
npm run build              # Production build
```

## API proxy

Vite dev server proxies `/api/*` → `http://localhost:8000` (api-gateway). Ensure api-gateway is running on port 8000 with proper backend localhost URLs.

## Key conventions

- **Shared constants**: All color/label maps live in `src/constants/labels.ts`. Pages import from there — never define inline maps.
- **Shared utils**: `formatFileSize()` and `formatDate()` are in `src/utils/format.ts`.
- **Routing**: All route definitions are in `src/router.tsx`. `App.tsx` only handles providers + rendering.
- **Error handling**: Use `ErrorBoundary` component to catch rendering errors. Use `InlineError` from `LoadingError.tsx` for API errors above tables.
- **Auth**: `AuthContext` is the only global state. Pages access it via `useAuth()` hook.
