# CLAUDE.md — frontend (M9)

## Role

Single-page application (React 19 + TypeScript 5 + Vite 8). Provides full UI for project management, document upload/knowledge base, task creation/tracking, output viewing with citation badges, and admin panel (users, groups, audit logs).

## Directory structure

```
frontend/
├── package.json
├── vite.config.ts            # Vite proxy → localhost:8000 (API gateway)
├── vitest.config.ts
├── tsconfig.json
├── README.md
├── src/
│   ├── App.tsx               # Router: login, projects, KB, tasks, output, admin, error pages
│   ├── main.tsx              # ReactDOM entry
│   ├── contexts/
│   │   └── AuthContext.tsx    # JWT storage, auto-refresh, 401 retry logic
│   ├── api/
│   │   ├── client.ts         # Axios: JWT injection, token refresh, error handling
│   │   ├── types.ts          # Full TypeScript type definitions (~6.5KB) — all API request/response types
│   │   ├── auth.ts           # Login/logout/refresh
│   │   ├── projects.ts       # Project CRUD
│   │   ├── documents.ts      # Document upload, list, delete
│   │   ├── tasks.ts          # Task create, poll, cancel, retry
│   │   ├── search.ts         # KB hybrid search
│   │   └── admin.ts          # User/group/audit management
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── ProjectList.tsx   # Table/card view toggle
│   │   ├── ProjectDetail.tsx # Sub-routes: KB, tasks
│   │   ├── KnowledgeBase.tsx # Drag-drop upload, document list, hybrid search
│   │   ├── TaskList.tsx      # Create task, status polling
│   │   ├── TaskOutput.tsx    # Markdown preview, color-coded citation badges
│   │   └── Admin/            # UserManagement, GroupManagement, AuditLogs
│   ├── components/
│   │   ├── MarkdownPreview.tsx # react-markdown renderer
│   │   ├── CitationBadge.tsx   # Green/Yellow/Red confidence badge
│   │   ├── DocumentUpload.tsx  # Drag-drop with progress
│   │   └── TaskProgress.tsx    # Progress bar with percentage
│   └── hooks/
│       ├── usePolling.ts     # Generic polling hook
│       └── useRequest.ts     # Loading/error state wrapper
```

## Route tree

```
/login                    → Login
/                         → Redirect to /projects
/projects                 → ProjectList
/projects/:id             → ProjectDetail
  /knowledge-base         → KnowledgeBase
  /tasks                  → TaskList
/projects/:id/tasks/:id   → TaskOutput
/admin/users              → UserManagement
/admin/groups             → GroupManagement
/admin/audit-logs         → AuditLogs
/403                      → Forbidden
/500                      → ServerError
*                         → NotFound
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
npm test                   # Vitest
npm run build              # Production build
```

## API proxy

Vite dev server proxies `/api/*` → `http://localhost:8000` (api-gateway). Ensure api-gateway is running on port 8000 with proper backend localhost URLs.
