# M1: API 网关 任务清单

> 目录：`api-gateway/` | 服务端口：8000

## 任务列表

### 项目初始化
- [ ] M1-01 初始化 FastAPI 项目结构，创建 `api-gateway/` 目录，配置 pyproject.toml/requirements.txt
- [ ] M1-02 创建配置管理模块，读取环境变量（JWT_SECRET、CORS_ORIGINS 等），支持 .env 文件
- [ ] M1-03 配置 Gunicorn + Uvicorn 启动入口，添加 health check 端点 `GET /health`
- [ ] M1-04 配置结构化日志（JSON 格式），区分 INFO/WARNING/ERROR 级别

### JWT 认证
- [ ] M1-05 实现 JWT 生成函数（access token 2h, refresh token 24h），payload 含 sub/username/role/group_ids
- [ ] M1-06 实现 JWT 验证中间件，解析 Authorization header，注入 request.state.user
- [ ] M1-07 实现 token 刷新端点 `POST /api/auth/refresh`，校验 refresh_token 后签发新 token 对
- [ ] M1-08 实现 token 黑名单机制（Redis set），logout 时将 token 加入黑名单

### RBAC 权限校验
- [ ] M1-09 实现 RBAC 权限矩阵（4 角色 × 6 操作），存储为常量配置
- [ ] M1-10 实现权限校验中间件，根据路由和用户角色判定是否放行，返回 403 时附带错误详情
- [ ] M1-11 实现项目组数据隔离辅助函数，从 token 提取 group_ids 并注入请求上下文
- [ ] M1-12 实现管理员权限检查装饰器/依赖项（system_admin / project_admin 区分）

### 限流
- [ ] M1-13 实现 Redis Token Bucket 限流器，支持按 user_id 和 IP 两个维度
- [ ] M1-14 配置限流策略：全局 100 req/min/user，上传 20 req/min，任务创建 10 req/min
- [ ] M1-15 实现限流中间件，超限返回 429 + Retry-After header
- [ ] M1-16 添加限流 metrics 暴露（Prometheus 格式），记录拒绝计数

### 审计日志
- [ ] M1-17 实现审计日志中间件，自动捕获 user_id/action/resource_type/resource_id/ip/ua
- [ ] M1-18 通过 Redis pub/sub 频道 `audit:log` 发送审计事件（解耦写入）
- [ ] M1-19 敏感操作（创建/删除/导出）记录 request body 摘要到 details 字段

### 路由与错误处理
- [ ] M1-20 实现路由注册表，将 `/api/auth/*` → user-service, `/api/projects/{id}/documents/*` → document-service 等规则配置化
- [ ] M1-21 实现统一错误响应格式化中间件，确保所有错误返回 `{"error": {"code": "...", "message": "..."}}` 格式
- [ ] M1-22 实现 CORS 中间件，从配置读取允许来源列表
- [ ] M1-23 实现请求体大小限制中间件（默认 100MB）
- [ ] M1-24 实现请求 ID 注入（X-Request-ID），贯穿整个请求生命周期

### 测试
- [ ] M1-25 编写 JWT 认证流程测试（登录成功/失败/token 过期/刷新）
- [ ] M1-26 编写 RBAC 权限矩阵测试（每个角色 × 每种操作的允许/拒绝）
- [ ] M1-27 编写限流测试（超限返回 429、恢复后正常）
- [ ] M1-28 编写审计日志中间件测试（事件是否正确发布到 Redis）