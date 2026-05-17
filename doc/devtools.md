# EconAI 开发环境软件清单

> 版本：v1.0 | 日期：2026-05-17

---

## 1. 容器运行时

| 软件 | 版本 | 安装方式 | 开发作用 |
|------|------|----------|----------|
| Colima | latest | `brew install colima` | macOS 轻量级容器运行时，替代 Docker Desktop。免费开源，基于 Lima，提供 containerd 运行环境 |
| Docker CLI | 29.x | `brew install docker` | Docker 命令行客户端，用于镜像构建（`docker build`）、容器管理（`docker run/ps/logs`） |
| Docker Compose | 5.x | `brew install docker-compose` | 多容器编排工具，一键启动 PostgreSQL/Redis/Milvus/MinIO 等全部基础设施服务，`docker compose up -d` |

> **说明**：开发和生产环境均使用 Docker Compose 管理服务。Colima 在本地提供 Docker 运行时，避免安装臃肿的 Docker Desktop（且 Docker Desktop 在大型机构需要商业许可）。

---

## 2. Python 生态

| 软件 | 版本 | 安装方式 | 开发作用 |
|------|------|----------|----------|
| Python | 3.12+ | `brew install python@3.12` | 项目运行时。选择 3.12 是因为部分 AI/ML 库（PyTorch、vLLM 客户端）对该版本兼容性最好 |
| uv | 0.11+ | `brew install uv` | 极速 Python 包管理器和虚拟环境工具（Rust 实现），替代 pip + venv。用于创建隔离的开发环境和锁定依赖 |
| FastAPI | 0.115+ | `uv add fastapi` | 异步 Web 框架，7 个微服务 + API 网关统一使用 |
| Pydantic | 2.x | `uv add pydantic` | 数据校验和序列化，用于 API 请求/响应模型、配置管理 |
| SQLAlchemy | 2.x (async) | `uv add sqlalchemy[asyncio]` | 异步 ORM，操作 PostgreSQL 业务数据库 |
| Alembic | latest | `uv add alembic` | 数据库迁移工具，版本化管理 schema 变更 |
| Celery | 5.x | `uv add celery` | 分布式异步任务队列，处理文档解析和 Agent 分析任务（后端 Redis） |
| Uvicorn | latest | `uv add uvicorn` | ASGI 服务器，各服务开发模式下的启动入口 |
| Gunicorn | latest | `uv add gunicorn` | 生产级 WSGI/ASGI 进程管理器，配合 Uvicorn workers 使用 |
| pytest | 8.x | `uv add --dev pytest pytest-asyncio pytest-mock` | 单元测试框架。pytest-asyncio 支持异步测试，pytest-mock 提供 mock 能力 |
| mypy | 1.x | `uv add --dev mypy` | 静态类型检查器（--strict 模式），确保所有函数有完整类型注解 |
| ruff | latest | `uv add --dev ruff` | Rust 实现的极速 Python linter + formatter，替代 flake8/isort/black |

### 各服务额外依赖

| 服务 | 额外包 | 用途 |
|------|--------|------|
| document-service | `pymupdf`, `pdfplumber`, `python-docx`, `openpyxl`, `pandas`, `python-pptx`, `beautifulsoup4`, `pytesseract`, `Pillow` | 多格式文档解析 + OCR |
| kb-service | `sentence-transformers`, `pymilvus` 或 `qdrant-client` | embedding 生成 + 向量数据库客户端 |
| llm-router | `anthropic`, `httpx` | Claude SDK + 本地 LLM HTTP 调用 |
| citation-service | `scikit-learn` | 语义相似度计算（cosine_similarity） |
| output-service | `python-docx`, `openpyxl`, `python-pptx`, `jinja2` | 多格式文件生成 |
| api-gateway | `python-jose[cryptography]`, `httpx`, `redis` | JWT + 反向代理 + 限流 |

---

## 3. 基础设施服务（Docker 容器）

以下服务通过 Docker Compose 启动，不需要本地安装：

| 服务 | 镜像 | 开发作用 |
|------|------|----------|
| PostgreSQL 16 | `postgres:16-alpine` | 业务数据库，存储用户/项目/文档/任务/引用/审计日志等全部业务数据。提供 FTS 全文搜索（BM25 索引）和 JSONB 支持 |
| Redis 7 | `redis:7-alpine` | 三重角色：Celery 消息队列（broker + backend）、JWT token 黑名单、API 限流计数器（Token Bucket）、服务间 pub/sub 事件总线 |
| Milvus | `milvusdb/milvus:latest` | 向量数据库，存储文档 chunk 的 embedding 向量（1024d），提供语义相似度检索 |
| MinIO | `minio/minio:latest` | S3 兼容对象存储，存放原始文档文件和生成的输出文件（.docx/.xlsx/.pptx） |
| Prometheus | `prom/prometheus:latest` | 监控指标采集，抓取各服务的 `/metrics` 端点 |
| Grafana | `grafana/grafana:latest` | 监控可视化面板，预置请求 QPS、延迟、错误率、任务耗时 Dashboard |
| Nginx | `nginx:alpine` | 反向代理 + TLS 终结 + 静态资源缓存 + 100MB 上传限制 |

---

## 4. Node.js 前端

| 软件 | 版本 | 安装方式 | 开发作用 |
|------|------|----------|----------|
| Node.js | 20 LTS 或 22+ | `brew install node@20` | JavaScript 运行时 |
| npm | 10.x | 随 Node.js | 包管理器 |
| TypeScript | 5.x | `npm install -D typescript` | 前端类型安全 |
| React | 19.x | `npm create vite@latest -- --template react-ts` | UI 框架 |
| Vite | 6.x | 随 Vite 模板 | 构建工具，开发模式 HMR 热重载 |
| Ant Design / Shadcn | latest | `npm install antd` 或 `npx shadcn-ui@latest init` | UI 组件库，企业级表格/表单/上传/弹窗 |

---

## 5. 其他工具

| 软件 | 版本 | 安装方式 | 开发作用 |
|------|------|----------|----------|
| git | 2.x | 系统自带 | 版本控制，每个模块完成后自动提交 |
| Tesseract | 5.x | `brew install tesseract` | OCR 引擎，处理扫描件 PDF 和图片文字识别（需 chi_sim 中文语言包） |

---

## 6. 一键安装命令

```bash
# === 容器运行时 ===
brew install colima docker docker-compose
colima start --cpu 4 --memory 8 --disk 60

# === Python 工具链 ===
brew install python@3.12 uv

# === OCR 引擎 ===
brew install tesseract
# 安装中文语言包（如果 brew 版本不自带）
# tesseract 5.x 通常已内置 chi_sim，验证: tesseract --list-langs | grep chi_sim

# === 前端 ===
# Node.js 通常已通过 brew 安装，确认版本:
node --version  # 应 >= 20

# === 启动基础设施服务 ===
cd /path/to/EconAI
docker compose up -d          # 启动 PostgreSQL / Redis / Milvus / MinIO / Nginx
docker compose ps              # 确认所有服务 healthy

# === 验证 ===
python3 --version              # >= 3.12
uv --version                   # >= 0.11
docker compose version         # >= 2.x
pytest --version               # >= 8.x
mypy --version                 # >= 1.x
ruff --version                 # >= 0.x
tesseract --version            # >= 5.x
```

---

*文档版本：v1.0 | 日期：2026-05-17 | 基于概要设计 v1.0 技术栈总览章节*