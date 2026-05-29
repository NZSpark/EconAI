# EconAI Role-Based Access Control (RBAC) Design

> Version: v2.0 | Date: 2026-05-24 | Derived from Requirements v2.0, High-Level Design v1.0, Detailed Design v1.0

---

## 1. Design Basis

The design goals, role definitions, and permission rules in this document are derived from the following three system design documents, **not the current code implementation**:

| Document | Version | Key Input |
|----------|---------|-----------|
| [Requirements (proposal.md)](./proposal.md) | v2.0 | §2 Target user personas, §6 Permission model and isolation rules |
| [High-Level Design (high-level-design.md)](./high-level-design.md) | v1.0 | §2.4 RBAC permission matrix, §5.1 API endpoint table, §8 Security architecture |
| [Detailed Design (detailed-design.md)](./detailed-design.md) | v1.0 | §2.4 Permission matrix, §9.2 Admin endpoint permissions, §9.4 Data isolation rules |

Deviations from code implementation are documented separately in §11.

---

## 2. User Roles

### 2.1 Role Definitions

> Source: [proposal.md §2.1](./proposal.md#21-user-personas)

| Role | Chinese Name | Positioning | Core Responsibilities |
|------|-------------|-------------|----------------------|
| `analyst` | Analyst | Primary daily user | Upload literature, configure knowledge sources, submit analysis tasks, view/export results |
| `senior_researcher` | Senior Researcher | Quality controller | Review source annotations, verify key claims, **approve report publication**, manage project creation |
| `project_admin` | Project Administrator | Group-level manager | Manage group members and permissions, configure knowledge base resources, **approve cross-group sharing** |
| `system_admin` | System Administrator | Platform operator | Global deployment operations, security management, audit log review, system configuration |

### 2.2 Key Role Differences

> Source: [proposal.md §6.1](./proposal.md#61-permission-model)

```
system_admin        Global management, no group boundary restrictions
    │
project_admin       Manage group members, projects, knowledge sources; approve cross-group sharing
    │
senior_researcher   Create projects, review and approve outputs, view all members' work in the group
    │
analyst             View projects, upload documents, initiate analysis tasks
```

**Two key design points** (from proposal.md):

1. **Senior Researchers have "review" permission** — "review analysis results, ensure academic quality", "review source annotations, verify key claims, approve report publication". This is the most fundamental distinction from analyst.
2. **Project Administrators have "cross-group authorization" capability** — "cross-group sharing requires explicit authorization from project administrator".

---

## 3. Organizational Model

### 3.1 Organizational Structure

> Source: [proposal.md §6.1](./proposal.md#61-permission-model)

```
Organization
├── Project Group A              ← Knowledge base and analysis result isolation boundary
│   ├── Analyst A1 (read-write)
│   ├── Analyst A2 (read-write)
│   └── Senior Researcher A3 (read-write+review)
├── Project Group B
│   ├── Project Admin B1 (read-write+review+manage)
│   └── ...
└── System Administrator (cross-group global)
```

### 3.2 Dual-Role System

A user's permissions in the system are jointly determined by two layers of roles:

| Layer | Storage Location | Meaning | Example |
|-------|-----------------|---------|---------|
| **System Role** | `users.role` | User's maximum capability ceiling on the platform | `analyst`, `senior_researcher`, `project_admin`, `system_admin` |
| **Group Role** | `project_group_members.role` | User's operational permissions within a specific project group | `analyst` (read-write), `senior_researcher` (read-write+review) |

**Effective Permission = System Role Ceiling ∩ Group Role Assignment**

For example: a `system_admin` marked as `analyst` within a group still has valid global operations from their system role; an `analyst` marked as `project_admin` within a group can only perform management operations within that group.

### 3.3 Isolation Rules

> Source: [proposal.md §6.2](./proposal.md#62-isolation-rules)

| Rule | Description |
|------|-------------|
| **Cross-group isolation** | Knowledge bases and analysis results between project groups are mutually invisible |
| **Intra-group visibility** | Senior researchers can view all members' work within the group |
| **Cross-group sharing** | Requires explicit authorization from project administrator |
| **Institutional knowledge base** | Access permissions can be configured per group |

---

## 4. Operation Definitions

### 4.1 Operation Categories

The complete operation set derived from API endpoint tables and user requirements in the three design documents:

| Operation | Enum Value | Description | Source |
|-----------|-----------|-------------|--------|
| **Research Operations** | | | |
| View Content | `view_content` | View projects, documents, tasks, search results | High-Level Design §2.4 |
| Create Project | `create_project` | Create new analysis project | Detailed Design §9.2.2 |
| Manage Project | `manage_project` | Update/delete/archive project | Detailed Design §9.2.2 PUT/DELETE |
| Upload Document | `upload_document` | Upload documents to project | Detailed Design §3.2.1 |
| Manage Document | `manage_document` | Delete documents, re-index | Detailed Design §3.2.4-5 |
| Create Task | `create_task` | Submit analysis task | Detailed Design §5.2.1 |
| Manage Task | `manage_task` | Cancel/retry task | Detailed Design §5.2.5-6 |
| Export Output | `export_output` | Download/export analysis results | Detailed Design §8.2.3 |
| **Review Operations** | | | |
| Review Output | `review_output` | Review source annotations, verify key claims | Requirements §2.1 Senior Researcher responsibilities |
| Approve Output | `approve_output` | Approve report for formal publication | Requirements §2.1 "approve report publication" |
| **Management Operations** | | | |
| Manage Members | `manage_members` | Add/remove group members, assign group roles | Detailed Design §9.2.3 |
| Manage Users | `manage_users` | Create/edit/list users (system-level) | Detailed Design §9.2.3 |
| Deactivate User | `deactivate_user` | Deactivate/delete user accounts | Detailed Design §9.2.3 DELETE |
| Create Group | `create_group` | Create new project group | Detailed Design §9.2.3 POST groups |
| Manage Group | `manage_group` | Edit/delete project group | Detailed Design §9.2.3 |
| Cross-Group Auth | `cross_group_auth` | Approve cross-group sharing of institutional KB | Requirements §6.2 |
| **Audit Operations** | | | |
| View Group Audit | `view_group_audit` | View group operation logs | Detailed Design §9.4 Data isolation |
| View All Audit | `view_all_audit` | View all platform operation logs | Detailed Design §9.2.3 |

### 4.2 Operation → Route Mapping

| Path Pattern | HTTP Method | Required Operation |
|-------------|------------|-------------------|
| `/api/projects` | GET | `view_content` |
| `/api/projects` | POST | `create_project` |
| `/api/projects/{id}` | GET | `view_content` |
| `/api/projects/{id}` | PUT/DELETE | `manage_project` |
| `/api/projects/{id}/search` | POST | `view_content` |
| `/api/projects/{id}/documents` | POST | `upload_document` |
| `/api/projects/{id}/documents/*` | GET | `view_content` |
| `/api/projects/{id}/documents/*` | DELETE | `manage_document` |
| `/api/projects/{id}/documents/*/reindex` | POST | `manage_document` |
| `/api/projects/{id}/tasks` | POST | `create_task` |
| `/api/projects/{id}/tasks` | GET | `view_content` |
| `/api/tasks/{id}` | GET | `view_content` |
| `/api/tasks/{id}/status` | GET | `view_content` |
| `/api/tasks/{id}/cancel` | POST | `manage_task` |
| `/api/tasks/{id}/retry` | POST | `manage_task` |
| `/api/tasks/{id}/output` | GET | `view_content` |
| `/api/tasks/{id}/output/review` | POST | `review_output` |
| `/api/tasks/{id}/output/approve` | POST | `approve_output` |
| `/api/tasks/{id}/export` | GET | `export_output` |
| `/api/institutional/search` | POST | `view_content` |
| `/api/admin/users` | GET | `manage_users` |
| `/api/admin/users` | POST | `manage_users` |
| `/api/admin/users/{id}` | PUT | `manage_users` |
| `/api/admin/users/{id}` | DELETE | `deactivate_user` |
| `/api/admin/groups` | GET | `manage_members` |
| `/api/admin/groups` | POST | `create_group` |
| `/api/admin/groups/{id}` | PUT/DELETE | `manage_group` |
| `/api/admin/groups/{id}/members` | POST | `manage_members` |
| `/api/admin/groups/{id}/members/{user_id}` | DELETE | `manage_members` |
| `/api/admin/groups/{id}/share` | POST | `cross_group_auth` |
| `/api/admin/audit-logs` | GET | `view_group_audit` / `view_all_audit` |

---

## 5. Permission Matrix

### 5.1 System Permission Matrix

> Core framework source: High-Level Design §2.4 and Detailed Design §2.4

| Operation | analyst | senior_researcher | project_admin | system_admin |
|-----------|---------|-------------------|---------------|--------------|
| `view_content` | ✅ Own group | ✅ Own group + all members | ✅ Own group | ✅ **All** |
| `create_project` | ❌ | ✅ Own group | ✅ Own group | ✅ **All** |
| `manage_project` | ❌ | ✅ Own group | ✅ Own group | ✅ **All** |
| `upload_document` | ✅ Own group | ✅ Own group | ✅ Own group | ✅ **All** |
| `manage_document` | ❌ | ✅ Own group | ✅ Own group | ✅ **All** |
| `create_task` | ✅ Own group | ✅ Own group | ✅ Own group | ✅ **All** |
| `manage_task` | ✅ Own only | ✅ All in group | ✅ Own group | ✅ **All** |
| `export_output` | ✅ Own group | ✅ Own group | ✅ Own group | ✅ **All** |
| `review_output` | ❌ | ✅ Own group | ✅ Own group | ✅ **All** |
| `approve_output` | ❌ | ✅ Own group | ✅ Own group | ✅ **All** |
| `manage_members` | ❌ | ❌ | ✅ Own group | ✅ **All** |
| `manage_users` | ❌ | ❌ | ✅ Own group users | ✅ **All** |
| `deactivate_user` | ❌ | ❌ | ❌ | ✅ **All** |
| `create_group` | ❌ | ❌ | ❌ | ✅ **All** |
| `manage_group` | ❌ | ❌ | ✅ Own group | ✅ **All** |
| `cross_group_auth` | ❌ | ❌ | ✅ Own group | ✅ **All** |
| `view_group_audit` | ❌ | ❌ | ✅ Own group | ✅ **All** |
| `view_all_audit` | ❌ | ❌ | ❌ | ✅ **All** |

### 5.2 Permission Matrix Derivation Notes

| Entry | Derivation Source |
|-------|------------------|
| `senior_researcher` has `review_output` and `approve_output` | Requirements §2.1: "review analysis results", "approve report publication" |
| `senior_researcher` has `manage_project` | Detailed Design §9.2.2: PUT/DELETE projects, senior researchers as project leads should have this capability |
| `senior_researcher`'s `view_content` includes viewing all group members' work | Requirements §2.1: "view all members' work in the group" |
| `analyst`'s `manage_task` limited to own tasks | Requirements §2.1: analysts are "primary daily users", cancel/retry limited to own tasks is reasonable |
| `project_admin` has no `create_group` | Detailed Design §9.2.3: "POST /api/admin/groups → system_admin". Group creation is platform-level |
| `project_admin` has `view_group_audit` | Detailed Design §9.4: "project_admin can see own group" audit logs |
| `project_admin` has `cross_group_auth` | Requirements §6.2: "cross-group sharing requires explicit authorization from project administrator" |
| `project_admin`'s `manage_users` limited to own group users | Requirements §6.2: administrators manage "own group" members and permissions |
| `analyst` / `senior_researcher` have no `manage_document` | Requirements §2.1: document management belongs to project management, handled by senior researchers and above |

### 5.3 Group Role Permissions

When a user is added to a project group, `project_group_members.role` determines their refined capabilities within the group:

| Group Role | Permissions | Corresponding System Role |
|------------|------------|--------------------------|
| `analyst` | Read-write (view, upload, create tasks, manage own tasks) | Matches `analyst` |
| `senior_researcher` | Read-write + review (including review, approve outputs) | Matches `senior_researcher` |
| `project_admin` | Read-write + review + manage group members | Matches `project_admin` |

---

## 6. Data Isolation

### 6.1 Isolation Rules

> Source: [proposal.md §6.2](./proposal.md#62-isolation-rules) and [detailed-design.md §9.4](./detailed-design.md#94-data-isolation-rules)

| Resource Type | analyst | senior_researcher | project_admin | system_admin |
|--------------|---------|-------------------|---------------|--------------|
| Projects | Own group | Own group (all) | Own group | All |
| Documents | Own group projects | Own group projects | Own group projects | All |
| Tasks | Own group projects | Own group projects (all members) | Own group projects | All |
| Task Outputs | Own group projects | Own group projects (all members) | Own group projects | All |
| Institutional KB | Own group | Own group | Own group + cross-group auth | All |
| User List | Not visible | Not visible | Own group members | All |
| Group List | Not visible | Not visible | Own group | All |
| Audit Logs | Not visible | Not visible | Own group | All |

### 6.2 Key Isolation Differences

| Role | Visibility Scope Difference |
|------|---------------------------|
| `analyst` | Only sees content within their participating groups, cannot see other analysts' tasks |
| `senior_researcher` | **Can view all group members' work** (source: Requirements §2.1), key difference from analyst |
| `project_admin` | Can view all group content + group audit logs, **can approve cross-group KB sharing** |
| `system_admin` | Crosses all group boundaries, global visibility |

---

## 7. Role Escalation Protection

### 7.1 Role Assignment Permissions

| Operator | Assignable System Roles | Cannot Assign |
|----------|------------------------|---------------|
| `system_admin` | `analyst`, `senior_researcher`, `project_admin`, `system_admin` | — |
| `project_admin` | `analyst`, `senior_researcher`, `project_admin` | `system_admin` |
| `senior_researcher` | — (no create/edit user permission) | All |
| `analyst` | — (no create/edit user permission) | All |

### 7.2 Group Role Assignment

| Operator | Assignable Group Roles |
|----------|----------------------|
| `project_admin` (own group) | `analyst`, `senior_researcher`, `project_admin` |
| `system_admin` | All group roles, any group |

### 7.3 Creating Project Groups

- **Only `system_admin` can create project groups** (source: Detailed Design §9.2.3 table)
- After creation, `system_admin` adds the first `project_admin` to the group
- Subsequently, the `project_admin` manages group members

---

## 8. Cross-Group Sharing Mechanism

> Source: [proposal.md §6.2](./proposal.md#62-isolation-rules)

```
Scenario: Project Group A's institutional KB needs to be shared with Project Group B

1. Project Group A's project_admin initiates a sharing request
   POST /api/admin/groups/{group_a}/share
   { "target_group_id": "group-b", "kb_segments": ["macro_data", "trade_policy"] }

2. Project Group B's project_admin receives notification and confirms (or system_admin approves)

3. After sharing takes effect:
   - Project Group B members can search Group A's authorized kb_segments in the institutional KB
   - Citation traceability still retains original source information
   - Sharing can be revoked at any time by project_admin or system_admin
```

---

## 9. Review Workflow

> Source: [proposal.md §2.1](./proposal.md#21-user-personas) Senior Researcher responsibilities

```
analyst creates task → task completes → output generated (status: draft)
                                    │
                                    ▼
                     senior_researcher reviews
                       ├── Review source annotations
                       ├── Verify key claims
                       └── Decide: Pass / Return for revision
                                    │
                         ┌──────────┴──────────┐
                         ▼                      ▼
                    Approved              Revision
                    Can export/publish    Analyst revises and resubmits
```

**Operation Mapping**:
| Operation | API | Role |
|-----------|-----|------|
| Submit for review | Auto-triggered on task completion | analyst |
| Review | `POST /api/tasks/{id}/output/review` | senior_researcher+ |
| Approve | `POST /api/tasks/{id}/output/approve` | senior_researcher+ |
| Return | `POST /api/tasks/{id}/output/review` (status=revision) | senior_researcher+ |

---

## 10. Error Codes

| Error Code | HTTP | Description |
|------------|------|-------------|
| `AUTH_TOKEN_MISSING` | 401 | Missing Bearer token |
| `AUTH_TOKEN_INVALID` | 401 | Token invalid or expired |
| `AUTH_TOKEN_BLACKLISTED` | 401 | Token has been revoked |
| `USER_PERMISSION_DENIED` | 403 | Role lacks permission for this operation |
| `USER_ROLE_ESCALATION` | 403 | Attempted to assign an unauthorized role |
| `USER_GROUP_OUT_OF_SCOPE` | 403 | Attempted to operate on non-group resource |
| `OUTPUT_NOT_REVIEWABLE` | 403 | Output not in reviewable state (e.g., task not completed) |
| `CROSS_GROUP_UNAUTHORIZED` | 403 | Cross-group sharing not authorized |

---

## 11. Deviations from Code Implementation

Current code (as of 2026-05-24) has the following deviations from this document's system design requirements:

| # | Requirement (Document) | Code Status | Deviation Description |
|---|----------------------|-------------|----------------------|
| 1 | `senior_researcher` has review capability | Not implemented | Missing `review_output`, `approve_output` operations and review workflow |
| 2 | `senior_researcher` can see all group members' work | Not implemented | API gateway and business layer group isolation doesn't distinguish analyst vs senior_researcher |
| 3 | `project_admin` can see group audit logs | Not implemented | Currently project_admin cannot access audit logs at all |
| 4 | `project_admin` can only manage own group users | Not isolated | `list_users` returns all users without group filtering |
| 5 | `project_admin` can only manage own groups | Not isolated | `list_groups` returns all groups without group filtering |
| 6 | Group creation only by `system_admin` | Code changed to allow project_admin too | Differs from Detailed Design §9.2.3, needs requirement confirmation |
| 7 | Missing `manage_project` operation | PUT/DELETE project maps to `view_project` | Anyone who can view a project can modify/delete |
| 8 | Missing cross-group sharing mechanism | Not implemented | Requirements §6.2 explicitly requires it |
| 9 | Missing group role system | `project_group_members.role` field not used for permission decisions | Requirements §6.1 explicitly distinguishes group roles |
| 10 | Missing review state machine | Output has no draft/approved/revision states | Requirements §2.1 senior researchers need to approve publication |

### 11.1 Implementation Priority

```
Phase 1 (Security Foundation):
  ├── #4 project_admin group isolation (user list filtering)
  ├── #5 project_admin group isolation (group list filtering)
  ├── #3 project_admin group audit logs
  └── #7 Add manage_project operation + route mapping

Phase 2 (Review System):
  ├── #1 Review operations (review_output / approve_output)
  ├── #10 Output review state machine (draft → approved / revision)
  └── #2 senior_researcher view all group members' work

Phase 3 (Advanced Features):
  ├── #8 Cross-group sharing mechanism
  ├── #9 Group role system
  └── #6 Group creation permission confirmation (align with Detailed Design)
```

---

## 12. Appendix: Configuration Items

| Config Item | Default | Description |
|-------------|---------|-------------|
| `JWT_ACCESS_EXPIRE_MINUTES` | 120 | Access token validity period (minutes) |
| `JWT_REFRESH_EXPIRE_HOURS` | 24 | Refresh token validity period (hours) |
| `TOKEN_BLACKLIST_ENABLED` | true | Whether to enable token blacklist |
| `RBAC_GROUP_SCOPING_ENABLED` | true | Whether to enable business service layer group isolation |
| `AUDIT_LOG_RETENTION_MONTHS` | 6 | Audit log retention months (Level 2 protection requirement) |

---

*Document version: v2.0 | Date: 2026-05-24 | Design source: Requirements v2.0 + High-Level Design v1.0 + Detailed Design v1.0*
