# M8: 用户权限服务 任务清单

> 目录：`services/user-service/` | 服务端口：8007

## 任务列表

### 项目初始化
- [x] M8-01 初始化 FastAPI 项目结构，创建 `services/user-service/` 目录，配置依赖
- [x] M8-02 创建配置管理模块（LDAP 参数、审计日志保留期、token 黑名单）

### 认证
- [x] M8-03 实现本地认证：用户名 + bcrypt 密码验证 → 查询 users 表
- [x] M8-04 实现登录端点 `POST /api/auth/login`：验证凭证 → 生成 access_token + refresh_token → 返回用户信息 + groups
- [x] M8-05 实现登出端点 `POST /api/auth/logout`：将 access_token 加入 Redis 黑名单（TTL=token 剩余有效期）
- [x] M8-06 实现当前用户端点 `GET /api/auth/me`：从 token 解析用户信息，返回 user_id/username/role/groups
- [x] M8-07 实现 token 黑名单校验函数：每次 token 验证时检查 Redis 黑名单

### LDAP/SSO
- [x] M8-08 实现 LDAP 认证：bind dn → 验证密码 → 查询或创建本地用户记录
- [x] M8-09 实现 LDAP 组映射：memberOf → 自动同步 project_group_members 关系
- [x] M8-10 实现 LDAP 连接池和超时处理
- [x] M8-11 实现 auth_provider 字段区分：local 用户 vs ldap 用户，ldap 用户不可修改密码

### RBAC 内部接口
- [x] M8-12 实现用户权限查询接口 `GET /internal/users/{user_id}/permissions`：返回 role, group_ids, project_ids
- [x] M8-13 实现项目权限校验接口 `POST /internal/permissions/check`：接收 user_id + project_id + action → 返回 allowed/denied

### 用户管理
- [x] M8-14 实现用户创建端点 `POST /api/admin/users`：username/email/display_name/role 校验，密码 bcrypt 哈希
- [x] M8-15 实现用户列表端点 `GET /api/admin/users`（分页 + role/status 过滤）
- [x] M8-16 实现用户更新端点 `PUT /api/admin/users/{id}`：更新 display_name/role/is_active
- [x] M8-17 实现用户停用端点 `DELETE /api/admin/users/{id}`：is_active=false（软删除，不删除数据）

### 项目组管理
- [x] M8-18 实现项目组创建端点 `POST /api/admin/groups`：name/description
- [x] M8-19 实现项目组列表端点 `GET /api/admin/groups`
- [x] M8-20 实现添加组成员端点 `POST /api/admin/groups/{id}/members`：group_id + user_id + role
- [x] M8-21 实现移除组成员端点 `DELETE /api/admin/groups/{id}/members/{user_id}`
- [x] M8-22 实现用户可见项目列表计算：通过 project_groups → projects 关联查询

### 项目管理 API
- [x] M8-23 实现创建项目端点 `POST /api/projects`：关联 group_id
- [x] M8-24 实现项目列表端点 `GET /api/projects`：按用户 group_ids 过滤可见项目（分页 + status 过滤）
- [x] M8-25 实现项目详情端点 `GET /api/projects/{id}`：含权限校验
- [x] M8-26 实现项目更新端点 `PUT /api/projects/{id}`
- [x] M8-27 实现项目归档端点 `DELETE /api/projects/{id}`：status=archived（软删除）

### 审计日志
- [x] M8-28 实现审计日志消费者：监听 Redis pub/sub `audit:log` → 写入 audit_logs 表
- [x] M8-29 实现审计日志查询端点 `GET /api/admin/audit-logs`（多条件过滤：user_id/action/resource_type/time range + 分页）
- [x] M8-30 审计日志表仅 INSERT，应用层 + 数据库层双重禁止 UPDATE/DELETE
- [ ] M8-31 实现审计日志定期归档：超过 retention_months 的记录导出到 MinIO 冷存储

### GDPR 合规
- [x] M8-32 实现数据访问权端点 `GET /api/user/data`：导出用户的所有个人数据（profile + 项目 + 文档 + 任务）
- [x] M8-33 实现数据删除权端点 `DELETE /api/user/data`：级联删除用户个人数据（profile 匿名化 + 项目/文档/任务级联）
- [x] M8-34 实现数据可携带权端点 `GET /api/user/data/export`：JSON 格式导出全部个人数据
- [x] M8-35 实现同意管理端点 `PUT /api/user/consent`：记录数据处理同意状态和时间戳

### 测试
- [x] M8-36 编写本地认证测试（登录成功/失败/token 过期/刷新/登出）
- [ ] M8-37 编写 LDAP 认证测试（mock LDAP server）
- [x] M8-38 编写 RBAC 权限校验测试（每个角色 × 每种操作的边界）
- [ ] M8-39 编写项目组隔离测试（跨组用户无法访问对方项目）
- [ ] M8-40 编写审计日志不可篡改测试（无 UPDATE/DELETE 权限）
- [ ] M8-41 编写 GDPR 数据删除测试（级联清理 + 匿名化）
- [ ] M8-42 编写用户 CRUD 测试（管理员权限校验）