# M10: 基础设施与部署 任务清单

> 目录：项目根目录 | 工具：Docker Compose, PostgreSQL, Redis, Milvus/Qdrant, MinIO, Nginx, Prometheus

## 任务列表

### Docker Compose
- [ ] M10-01 创建根目录 `docker-compose.yml`：定义所有服务（api-gateway, 7 个微服务, PostgreSQL, Redis, Milvus, MinIO, Nginx, Prometheus, Grafana）
- [ ] M10-02 为每个微服务创建 `Dockerfile`（多阶段构建，基础镜像 python:3.12-slim）
- [ ] M10-03 创建 `.env.template` 模板文件，列出所有环境变量及默认值
- [ ] M10-04 创建 `docker-compose.override.yml` 用于本地开发（挂载源码目录、热重载）

### PostgreSQL
- [ ] M10-05 创建数据库初始化 SQL 脚本 `db/init/01-schema.sql`：创建所有表（users, project_groups, project_group_members, projects, documents, document_chunks, analysis_tasks, task_outputs, citations, audit_logs, llm_usage_logs）
- [ ] M10-06 创建索引初始化 SQL 脚本：所有索引（含 GIN 索引用于 FTS）
- [ ] M10-07 创建数据库迁移工具配置（Alembic），支持版本化 schema 变更
- [ ] M10-08 创建种子数据脚本 `db/seed.sql`：默认 admin 用户 + 示例项目组
- [ ] M10-09 配置 PostgreSQL FTS：中文分词字典（zhparser 或简单 jieba 分词）

### Redis
- [ ] M10-10 配置 Redis：持久化策略（RDB + AOF）、最大内存限制
- [ ] M10-11 定义 Redis key 命名规范：`ratelimit:*`, `token:blacklist:*`, `kb:index:*`, `audit:*`

### 向量数据库
- [ ] M10-12 创建 Milvus/Qdrant 初始化配置：collection/field schema（chunk_id, vector(1024d), project_id, document_id, chunk_type）
- [ ] M10-13 创建索引创建脚本（IVF_FLAT 或 HNSW，nlist 参数）
- [ ] M10-14 配置向量数据库持久化和备份策略

### MinIO
- [ ] M10-15 配置 MinIO：创建 buckets（econai-documents, econai-outputs）、访问策略
- [ ] M10-16 配置 MinIO 生命周期规则（文档临时文件自动过期）
- [ ] M10-17 生成 MinIO access key/secret key，写入各服务环境变量

### Nginx
- [ ] M10-18 配置 Nginx 反向代理：upstream 定义（api-gateway:8000）
- [ ] M10-19 配置 TLS 终结（自签名证书用于开发，生产用机构证书）
- [ ] M10-20 配置客户端请求体大小限制（100MB）
- [ ] M10-21 配置 gzip 压缩、静态资源缓存 header

### Celery
- [ ] M10-22 创建 Celery 配置模块：broker(Redis) + backend(Redis) + 队列定义（document, orchestration）
- [ ] M10-23 创建 Celery Beat 定时任务配置（审计日志定期归档）
- [ ] M10-24 配置 Celery worker 并发数和内存限制

### 监控
- [ ] M10-25 配置 Prometheus：抓取目标（api-gateway, 各微服务的 /metrics 端点）
- [ ] M10-26 为每个服务添加 Prometheus metrics 暴露（prometheus-fastapi-instrumentator）
- [ ] M10-27 配置 Grafana：数据源（Prometheus）+ 预置 dashboard（请求 QPS/延迟/错误率/任务耗时）
- [ ] M10-28 配置告警规则：任务失败率 > 10%、API 延迟 > 5s、向量库不可用、磁盘使用率 > 80%

### 部署
- [ ] M10-29 创建 `docker-compose.prod.yml`：生产环境配置（资源限制、日志驱动、健康检查）
- [ ] M10-30 创建部署文档脚本 `deploy.sh`：一键启动/停止/查看状态
- [ ] M10-31 配置各服务的 health check（`/health` 端点 + depends_on 依赖顺序）

### 测试
- [ ] M10-32 编写 Docker Compose 启动测试（所有服务健康检查通过）
- [ ] M10-33 编写数据库迁移测试（upgrade/downgrade 无报错）
- [ ] M10-34 编写种子数据连接测试（默认用户能成功登录）