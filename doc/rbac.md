# PolicyAI 角色与权限体系设计（RBAC）

> 版本：v2.0 | 日期：2026-05-24 | 基于需求文档 v2.0、概要设计 v1.0、详细设计 v1.0 的系统需求推导，非代码实现照搬

---

## 1. 设计依据

本文档的设计目标、角色定义和权限规则来源于以下三份系统设计文档，**而非当前代码实现**：

| 文档 | 版本 | 关键输入 |
|------|------|----------|
| [需求文档 (proposal.md)](./proposal.md) | v2.0 | §2 目标用户画像、§6 权限模型与隔离规则 |
| [概要设计 (high-level-design.md)](./high-level-design.md) | v1.0 | §2.4 RBAC 权限矩阵、§5.1 API 端点表、§8 安全架构 |
| [详细设计 (detailed-design.md)](./detailed-design.md) | v1.0 | §2.4 权限矩阵、§9.2 管理端点权限、§9.4 数据隔离规则 |

代码实现的偏差在 §11 中单独说明。

---

## 2. 用户角色

### 2.1 角色定义

> 来源：[proposal.md §2.1](./proposal.md#21-用户画像)

| 角色 | 中文名称 | 定位 | 核心职责 |
|------|----------|------|----------|
| `analyst` | 分析员 | 日常主力用户 | 上传文献、配置知识源、提交分析任务、查看/导出结果 |
| `senior_researcher` | 高级研究员 | 质量把控者 | 审查来源标注、校验关键论断、**批准报告发布**、管理项目创建 |
| `project_admin` | 项目管理员 | 组级管理者 | 管理项目组成员和权限、配置知识库资源、**审批跨组共享** |
| `system_admin` | 系统管理员 | 平台运营者 | 全局部署运维、安全管理、审计日志审查、系统配置 |

### 2.2 角色的关键差异

> 来源：[proposal.md §6.1](./proposal.md#61-权限模型)

```
system_admin        全局管理，无组边界限制
    │
project_admin       管理本组成员、项目、知识源；审批跨组共享
    │
senior_researcher   创建项目、审阅和批准输出、查看本组所有成员工作
    │
analyst             查看项目、上传文档、发起分析任务
```

**两个关键设计点**（来自 proposal.md）：

1. **高级研究员有「审核」权限**——"审核分析结果，把控学术质量"、"审查来源标注、校验关键论断、批准报告发布"。这是与 analyst 最本质的区别。
2. **项目管理员有「跨组授权」能力**——"跨组共享需项目管理员显式授权"。

---

## 3. 组织模型

### 3.1 组织结构

> 来源：[proposal.md §6.1](./proposal.md#61-权限模型)

```
组织
├── 项目组 A                    ← 知识库和分析结果隔离边界
│   ├── 分析员 A1 (读写)
│   ├── 分析员 A2 (读写)
│   └── 高级研究员 A3 (读写+审核)
├── 项目组 B
│   ├── 项目管理员 B1 (读写+审核+管理)
│   └── ...
└── 系统管理员 (跨组全局)
```

### 3.2 双重角色体系

用户在系统中的权限由两层角色共同决定：

| 层 | 存储位置 | 含义 | 示例 |
|----|----------|------|------|
| **系统角色** | `users.role` | 用户在平台上的最高能力上限 | `analyst`、`senior_researcher`、`project_admin`、`system_admin` |
| **组内角色** | `project_group_members.role` | 用户在特定项目组内的操作权限 | `analyst`（读写）、`senior_researcher`（读写+审核） |

**有效权限 = 系统角色上限 ∩ 组内角色分配**

例如：一个 `system_admin` 即使在某组内被标记为 `analyst`，其系统角色允许的全局操作仍然有效；一个 `analyst` 在某组内被标记为 `project_admin`，也仅能在该组内做管理操作。

### 3.3 隔离规则

> 来源：[proposal.md §6.2](./proposal.md#62-隔离规则)

| 规则 | 说明 |
|------|------|
| **组间隔离** | 项目组间的知识库和分析结果互不可见 |
| **组内可见** | 高级研究员可查看本组所有成员的工作成果 |
| **跨组共享** | 需项目管理员显式授权 |
| **机构知识库** | 可按组配置访问权限 |

---

## 4. 操作定义

### 4.1 操作分类

从三份设计文档的 API 端点表和用户需求中，推导出完整的操作集：

| 操作 | 枚举值 | 说明 | 来源 |
|------|--------|------|------|
| **研究操作** | | | |
| 查看内容 | `view_content` | 查看项目、文档、任务、搜索结果 | 概要设计 §2.4 |
| 创建项目 | `create_project` | 新建分析项目 | 详细设计 §9.2.2 |
| 管理项目 | `manage_project` | 更新/删除/归档项目 | 详细设计 §9.2.2 PUT/DELETE |
| 上传文档 | `upload_document` | 向项目上传文档 | 详细设计 §3.2.1 |
| 管理文档 | `manage_document` | 删除文档、重新索引 | 详细设计 §3.2.4-5 |
| 创建任务 | `create_task` | 提交分析任务 | 详细设计 §5.2.1 |
| 管理任务 | `manage_task` | 取消/重试任务 | 详细设计 §5.2.5-6 |
| 导出输出 | `export_output` | 下载/导出分析结果 | 详细设计 §8.2.3 |
| **审核操作** | | | |
| 审阅输出 | `review_output` | 审查来源标注、校验关键论断 | 需求文档 §2.1 高级研究员职责 |
| 批准发布 | `approve_output` | 批准报告正式发布 | 需求文档 §2.1 "批准报告发布" |
| **管理操作** | | | |
| 管理组成员 | `manage_members` | 添加/移除项目组成员、分配组内角色 | 详细设计 §9.2.3 |
| 管理用户 | `manage_users` | 创建/编辑/列表用户（系统级） | 详细设计 §9.2.3 |
| 停用用户 | `deactivate_user` | 停用/删除用户账号 | 详细设计 §9.2.3 DELETE |
| 创建项目组 | `create_group` | 创建新的项目组 | 详细设计 §9.2.3 POST groups |
| 管理项目组 | `manage_group` | 编辑/删除项目组 | 详细设计 §9.2.3 |
| 跨组授权 | `cross_group_auth` | 审批机构知识库的跨组共享 | 需求文档 §6.2 |
| **审计操作** | | | |
| 查看本组审计 | `view_group_audit` | 查看本组操作日志 | 详细设计 §9.4 数据隔离 |
| 查看全局审计 | `view_all_audit` | 查看全平台操作日志 | 详细设计 §9.2.3 |

### 4.2 操作 → 路由映射

| 路径模式 | HTTP 方法 | 所需操作 |
|----------|-----------|----------|
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

## 5. 权限矩阵

### 5.1 系统权限矩阵

> 核心框架来源：概要设计 §2.4 和 详细设计 §2.4

| 操作 | analyst | senior_researcher | project_admin | system_admin |
|------|---------|-------------------|---------------|--------------|
| `view_content` | ✅ 本组 | ✅ 本组 + 本组全部成员 | ✅ 本组 | ✅ **全部** |
| `create_project` | ❌ | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `manage_project` | ❌ | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `upload_document` | ✅ 本组 | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `manage_document` | ❌ | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `create_task` | ✅ 本组 | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `manage_task` | ✅ 仅自己 | ✅ 本组全部 | ✅ 本组 | ✅ **全部** |
| `export_output` | ✅ 本组 | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `review_output` | ❌ | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `approve_output` | ❌ | ✅ 本组 | ✅ 本组 | ✅ **全部** |
| `manage_members` | ❌ | ❌ | ✅ 本组 | ✅ **全部** |
| `manage_users` | ❌ | ❌ | ✅ 本组用户 | ✅ **全部** |
| `deactivate_user` | ❌ | ❌ | ❌ | ✅ **全部** |
| `create_group` | ❌ | ❌ | ❌ | ✅ **全部** |
| `manage_group` | ❌ | ❌ | ✅ 本组 | ✅ **全部** |
| `cross_group_auth` | ❌ | ❌ | ✅ 本组 | ✅ **全部** |
| `view_group_audit` | ❌ | ❌ | ✅ 本组 | ✅ **全部** |
| `view_all_audit` | ❌ | ❌ | ❌ | ✅ **全部** |

### 5.2 权限矩阵推导说明

| 条目 | 推导来源 |
|------|----------|
| `senior_researcher` 有 `review_output` 和 `approve_output` | 需求文档 §2.1："审核分析结果"、"批准报告发布" |
| `senior_researcher` 有 `manage_project` | 详细设计 §9.2.2：PUT/DELETE 项目，高级研究员作为组内项目负责人应有此能力 |
| `senior_researcher` 的 `view_content` 包含查看本组全部成员工作 | 需求文档 §2.1："查看本组所有成员的工作成果" |
| `analyst` 的 `manage_task` 仅限自己创建的任务 | 需求文档 §2.1：分析师是"日常使用的主力用户"，取消/重试仅限自己的任务合理 |
| `project_admin` 无 `create_group` | 详细设计 §9.2.3："POST /api/admin/groups → system_admin"。创建组是平台级操作 |
| `project_admin` 有 `view_group_audit` | 详细设计 §9.4："project_admin 可见本组"审计日志 |
| `project_admin` 有 `cross_group_auth` | 需求文档 §6.2："跨组共享需项目管理员显式授权" |
| `project_admin` 的 `manage_users` 仅限本组用户 | 需求文档 §6.2：管理员管理的是"本组"成员和权限 |
| `analyst` / `senior_researcher` 无 `manage_document` | 需求文档 §2.1：文档管理属于项目管理范畴，由高级研究员及以上负责 |

### 5.3 组内角色权限

当用户被添加到项目组时，`project_group_members.role` 决定其在组内的细化能力：

| 组内角色 | 权限 | 对应系统角色 |
|----------|------|-------------|
| `analyst` | 读写（查看、上传、创建任务、管理自己的任务） | 匹配 `analyst` |
| `senior_researcher` | 读写 + 审核（含审阅、批准输出） | 匹配 `senior_researcher` |
| `project_admin` | 读写 + 审核 + 管理组成员 | 匹配 `project_admin` |

---

## 6. 数据隔离

### 6.1 隔离规则

> 来源：[proposal.md §6.2](./proposal.md#62-隔离规则) 和 [detailed-design.md §9.4](./detailed-design.md#94-数据隔离规则)

| 资源类型 | analyst | senior_researcher | project_admin | system_admin |
|----------|---------|-------------------|---------------|--------------|
| 项目 | 本组 | 本组（全部） | 本组 | 全部 |
| 文档 | 本组项目 | 本组项目 | 本组项目 | 全部 |
| 任务 | 本组项目 | 本组项目（全部成员） | 本组项目 | 全部 |
| 任务输出 | 本组项目 | 本组项目（全部成员） | 本组项目 | 全部 |
| 机构知识库 | 本组 | 本组 | 本组 + 跨组授权 | 全部 |
| 用户列表 | 不可见 | 不可见 | 本组成员 | 全部 |
| 项目组列表 | 不可见 | 不可见 | 本组 | 全部 |
| 审计日志 | 不可见 | 不可见 | 本组 | 全部 |

### 6.2 关键隔离差异

| 角色 | 可见范围差异 |
|------|-------------|
| `analyst` | 仅看到自己参与的项目组内的内容，看不到其他分析师的任务 |
| `senior_researcher` | **可查看本组所有成员的工作**（来源：需求文档 §2.1），这是与 analyst 的关键区别 |
| `project_admin` | 可查看本组所有内容 + 本组审计日志，**可审批跨组知识库共享** |
| `system_admin` | 跨所有组边界，全局可见 |

---

## 7. 角色提权保护

### 7.1 角色分配权限

| 操作者 | 可分配的系统角色 | 不可分配 |
|--------|-----------------|----------|
| `system_admin` | `analyst`, `senior_researcher`, `project_admin`, `system_admin` | — |
| `project_admin` | `analyst`, `senior_researcher`, `project_admin` | `system_admin` |
| `senior_researcher` | —（无权创建/编辑用户） | 全部 |
| `analyst` | —（无权创建/编辑用户） | 全部 |

### 7.2 组内角色分配

| 操作者 | 可分配的组内角色 |
|--------|-----------------|
| `project_admin`（本组） | `analyst`, `senior_researcher`, `project_admin` |
| `system_admin` | 全部组内角色，任意组 |

### 7.3 创建项目组

- **仅 `system_admin` 可创建项目组**（来源：详细设计 §9.2.3 表格）
- 创建后，`system_admin` 将第一个 `project_admin` 加入组
- 之后由该 `project_admin` 管理组成员

---

## 8. 跨组共享机制

> 来源：[proposal.md §6.2](./proposal.md#62-隔离规则)

```
场景：项目组 A 的机构知识库需要共享给项目组 B

1. 项目组 A 的 project_admin 发起共享请求
   POST /api/admin/groups/{group_a}/share
   { "target_group_id": "group-b", "kb_segments": ["macro_data", "trade_policy"] }

2. 项目组 B 的 project_admin 获得通知并确认（或 system_admin 审批）

3. 共享生效后：
   - 项目组 B 的成员在搜索机构知识库时，可检索到 A 组已授权的 kb_segments
   - 引用溯源依然保留原始来源信息
   - 共享可随时由 project_admin 或 system_admin 撤销
```

---

## 9. 审核工作流

> 来源：[proposal.md §2.1](./proposal.md#21-用户画像) 高级研究员职责

```
analyst 创建任务 → 任务完成 → 生成输出（状态: draft）
                                    │
                                    ▼
                     senior_researcher 审阅
                       ├── 审查来源标注
                       ├── 校验关键论断
                       └── 决定: 通过 / 退回修改
                                    │
                         ┌──────────┴──────────┐
                         ▼                      ▼
                    批准 (approved)        退回 (revision)
                    可导出/发布            analyst 修改后重新提交
```

**操作映射**：
| 操作 | API | 角色 |
|------|-----|------|
| 提交审核 | 任务完成自动触发 | analyst |
| 审阅 | `POST /api/tasks/{id}/output/review` | senior_researcher+ |
| 批准 | `POST /api/tasks/{id}/output/approve` | senior_researcher+ |
| 退回 | `POST /api/tasks/{id}/output/review` (status=revision) | senior_researcher+ |

---

## 10. 错误码

| 错误码 | HTTP | 说明 |
|--------|------|------|
| `AUTH_TOKEN_MISSING` | 401 | 缺少 Bearer token |
| `AUTH_TOKEN_INVALID` | 401 | Token 无效或已过期 |
| `AUTH_TOKEN_BLACKLISTED` | 401 | Token 已被撤销 |
| `USER_PERMISSION_DENIED` | 403 | 角色无权执行该操作 |
| `USER_ROLE_ESCALATION` | 403 | 尝试分配无权授予的角色 |
| `USER_GROUP_OUT_OF_SCOPE` | 403 | 尝试操作非本组资源 |
| `OUTPUT_NOT_REVIEWABLE` | 403 | 输出不在可审阅状态（如任务未完成） |
| `CROSS_GROUP_UNAUTHORIZED` | 403 | 跨组共享未经授权 |

---

## 11. 与代码实现的差异

当前代码（截至 2026-05-24）与本文档的系统设计需求存在以下偏差：

| # | 需求（文档要求） | 代码现状 | 偏差说明 |
|---|-----------------|----------|----------|
| 1 | `senior_researcher` 有审核能力 | 未实现 | 缺少 `review_output`、`approve_output` 操作和审核工作流 |
| 2 | `senior_researcher` 可见本组全部成员工作 | 未实现 | API 网关层和业务层的组隔离未区分 analyst vs senior_researcher |
| 3 | `project_admin` 可见本组审计日志 | 未实现 | 当前 project_admin 完全无法访问审计日志 |
| 4 | `project_admin` 仅可管理本组用户 | 未隔离 | `list_users` 返回全量用户，未做组过滤 |
| 5 | `project_admin` 仅可管理本组 | 未隔离 | `list_groups` 返回全量组，未做组过滤 |
| 6 | 创建项目组仅 `system_admin` | 代码已改为 project_admin 也可 | 与详细设计 §9.2.3 不同，需确认需求 |
| 7 | 缺少 `manage_project` 操作 | PUT/DELETE 项目映射到 `view_project` | 任何可查看项目的人都能修改/删除 |
| 8 | 缺少跨组共享机制 | 未实现 | 需求文档 §6.2 明确要求 |
| 9 | 缺少组内角色体系 | `project_group_members.role` 字段未用于权限判断 | 需求文档 §6.1 明确区分组内角色 |
| 10 | 缺少审核状态机 | 输出无 draft/approved/revision 状态 | 需求文档 §2.1 高级研究员需批准发布 |

### 11.1 实现优先级

```
Phase 1 (安全基础):
  ├── #4 project_admin 组隔离（用户列表过滤）
  ├── #5 project_admin 组隔离（组列表过滤）
  ├── #3 project_admin 本组审计日志
  └── #7 新增 manage_project 操作 + 路由映射

Phase 2 (审核体系):
  ├── #1 审核操作（review_output / approve_output）
  ├── #10 输出审核状态机（draft → approved / revision）
  └── #2 senior_researcher 查看本组全部成员工作

Phase 3 (高级功能):
  ├── #8 跨组共享机制
  ├── #9 组内角色体系
  └── #6 创建项目组权限确认（与详细设计保持一致）
```

---

## 12. 附录：配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `JWT_ACCESS_EXPIRE_MINUTES` | 120 | Access token 有效期（分钟） |
| `JWT_REFRESH_EXPIRE_HOURS` | 24 | Refresh token 有效期（小时） |
| `TOKEN_BLACKLIST_ENABLED` | true | 是否启用 Token 黑名单 |
| `RBAC_GROUP_SCOPING_ENABLED` | true | 是否启用业务服务层组隔离 |
| `AUDIT_LOG_RETENTION_MONTHS` | 6 | 审计日志保留月数（等保二级要求） |

---

*文档版本：v2.0 | 日期：2026-05-24 | 设计来源：需求文档 v2.0 + 概要设计 v1.0 + 详细设计 v1.0*
