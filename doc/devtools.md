# PolicyAI 开发环境软件清单

> 版本：v2.0 | 日期：2026-05-21

基于所有 10 个模块的 `pyproject.toml`、`package.json` 及实际运行环境。

---

## 1. 容器运行时

| 软件 | 版本 | 安装方式 | 开发作用 |
|------|------|----------|----------|
| Colima | 0.10.x | `brew install colima` | macOS 轻量级容器运行时，替代 Docker Desktop。基于 Lima，提供 containerd 运行环境 |
| Docker CLI | 29.5.x | `brew install docker` | 镜像构建（`docker build`）、容器管理 |
| Docker Compose | 5.1.x | `brew install docker-compose` | 多容器编排，一键启动 PostgreSQL / Redis / Milvus / MinIO / Nginx / Prometheus / Grafana |

**容器内的基础设施服务：**

| 服务 | 镜像 | 作用 |
|------|------|------|
| PostgreSQL 16 | `postgres:16-alpine` | 业务数据库 + FTS 全文搜索（BM25）+ JSONB |
| Redis 7 | `redis:7-alpine` | Celery broker/backend + Token 黑名单 + 限流计数器 + pub/sub 事件总线 |
| Milvus | `milvusdb/milvus:latest` | 向量数据库，存储 embedding（1024d），语义相似度检索 |
| MinIO | `minio/minio:latest` | S3 兼容对象存储，存放文档和输出文件 |
| Nginx | `nginx:alpine` | 反向代理 + TLS 终结 + 静态资源缓存 + 100MB 上传限制 |
| Prometheus | `prom/prometheus:latest` | 监控指标采集 |
| Grafana | `grafana/grafana:latest` | 监控面板 |

---

## 2. Python 生态

| 软件 | 版本 | 安装方式 | 开发作用 |
|------|------|----------|----------|
| Python | 3.14.5 (>=3.12) | `brew install python@3.14` | 运行时 |
| uv | 0.11.9 | `brew install uv` | 极速包管理器 + 虚拟环境（Rust 实现），替代 pip + venv |

### 2.1 微服务框架

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| fastapi | >=0.115 | 全部 7 服务 + 网关 | 异步 Web 框架 |
| uvicorn | >=0.30 | 全部 | ASGI 开发服务器 |
| gunicorn | latest | M10 编排 | 生产级 ASGI 进程管理器 |
| pydantic | >=2.0 | 全部 | 数据校验 / 序列化 |
| pydantic-settings | >=2.0 | 全部 | 环境变量 / .env 配置管理 |
| python-multipart | >=0.0.12 | M1, M2, M8 | multipart/form-data 文件上传解析 |
| pyyaml | >=6.0 | M1, M5, M7 | YAML 配置解析 |

### 2.2 数据库与存储

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| sqlalchemy[asyncio] | >=2.0 | M2, M6, M7, M8 | 异步 ORM（PostgreSQL） |
| asyncpg | >=0.29 | M2, M3, M6, M7, M8 | PostgreSQL 异步驱动 |
| alembic | >=1.13 | M8 | 数据库迁移版本管理 |
| redis | >=5.0 | M1, M2, M3, M4, M5, M6 | Redis 客户端（限流/缓存/队列/pub-sub） |
| minio | >=7.0 | M2, M7 | S3 兼容对象存储客户端 |

### 2.3 异步任务

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| celery[redis] | >=5.4 | M2, M4 | 分布式任务队列（Redis 后端），文档解析 + Agent 分析 |

### 2.4 认证与安全

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| python-jose[cryptography] | >=3.3 | M1 | JWT 签发 / 验证 |
| bcrypt | >=4.2 | M8 | 密码哈希 |
| pyjwt | >=2.9 | M8 | JWT token 编解码 |
| python-ldap | >=3.4 | M8 | LDAP/AD 认证集成 |

### 2.5 LLM 与 AI

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| anthropic | >=0.39 | M5 | Claude Messages API SDK（含 tool_use 双向转换） |
| httpx | >=0.27 | M1, M2, M3, M4, M5 | 异步 HTTP 客户端（反向代理 + 服务间调用） |
| numpy | >=1.26 | M6 | 向量运算（cosine_similarity 等） |
| tiktoken | >=0.7 | M2 | Token 计数（精确控制 chunk 大小） |

### 2.6 文档解析（document-service 专用）

| 包 | 版本 | 作用 |
|----|------|------|
| pymupdf | >=1.24 | PDF 解析（基于 MuPDF） |
| pdfplumber | latest | PDF 表格/文本精细提取 |
| python-docx | >=1.1 | Word .docx 读写 |
| openpyxl | >=3.1 | Excel .xlsx 读写 |
| pandas | >=2.2 | CSV / 表格数据处理 |
| python-pptx | >=0.6 | PowerPoint .pptx 解析 |
| beautifulsoup4 | >=4.12 | HTML / MHTML 解析 |
| lxml | >=5.0 | XML/HTML 高性能解析 |
| pillow | >=10.0 | 图片处理（OCR 预处理） |

### 2.7 输出生成（output-service 专用）

| 包 | 版本 | 作用 |
|----|------|------|
| python-docx | >=1.0 | .docx 生成（GB/T 9704 公文国标） |
| openpyxl | >=3.1 | .xlsx 生成（对比矩阵 + 引用清单） |
| python-pptx | >=1.0 | .pptx 生成（简报） |
| jinja2 | >=3.1 | Markdown/文本模板渲染 |

### 2.8 可观测性

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| structlog | >=24.0 | M1 | 结构化 JSON 日志 |
| starlette-prometheus | >=0.10 | M1 | `/metrics` 端点暴露 |
| prometheus-client | >=0.18 | M1 | Prometheus 指标采集 |

### 2.9 共享包

| 包 | 版本 | 适用模块 | 作用 |
|----|------|----------|------|
| policyai-shared | 0.1.0 (本地) | M2, M3, M4 | Pydantic models + 配置加载器 + 结构化日志 |

### 2.10 开发工具

| 软件 | 版本 | 作用 |
|------|------|------|
| pytest | 9.0.3 | 单元测试框架（所有模块） |
| pytest-asyncio | 1.3.0 | 异步测试支持 |
| pytest-mock | 3.15.1 | Mock 能力（纯 mock，零外部依赖） |
| mypy | 2.1.0 | 静态类型检查（除 llm-router/user-service 外均为 `strict = true`） |
| ruff | 0.15.13 | Rust 实现的高速 linter + formatter，替代 flake8/isort/black |

**mypy 配置差异：**

| 模块 | strict | ignore_missing_imports | 备注 |
|------|--------|------------------------|------|
| shared | yes | yes | - |
| api-gateway | yes | no (except jose*) | 最严格，仅 jose 豁免 |
| document-service | yes | yes | disallow_untyped_decorators = false |
| kb-service | yes | yes | 同 document-service |
| llm-router | no (逐项开关) | yes | 半严格模式 |
| orchestration-service | yes | yes | 同 document-service |
| output-service | yes | yes | 禁用 no-untyped-call, valid-type |
| citation-service | yes | yes | - |
| user-service | no (逐项开关) | yes | exclude alembic/ + tests/ |

**ruff lint 规则选择差异：**

| 模块 | 规则集 | 备注 |
|------|--------|------|
| 大部分模块 | E, F, I, N, W, UP, B, SIM | 标准规则集 |
| api-gateway | E, W, F, I, B, C4, UP | 增加 C4 (flake8-comprehensions) |
| user-service | E, F, I, N, W, UP, B, C4, SIM | 增加 C4 |
| shared | E, F, I, N, W, UP, B, C4, SIM | 增加 C4 |

---

## 3. Node.js 前端

| 软件 | 版本 | 安装方式 | 作用 |
|------|------|----------|------|
| Node.js | 26.x | `brew install node` | JavaScript 运行时 |
| npm | 11.12.x | 随 Node.js | 包管理器 |

### 3.1 运行时依赖

| 包 | 版本 | 作用 |
|----|------|------|
| react | 19.2.x | UI 框架 |
| react-dom | 19.2.x | React DOM 渲染 |
| react-router-dom | 7.15.x | 前端路由（登录/项目/知识库/任务/管理） |
| antd | 6.4.x | Ant Design UI 组件库 |
| @ant-design/icons | 6.2.x | Ant Design 图标库 |
| axios | 1.16.x | HTTP 客户端（JWT 自动注入 + 401 刷新重试） |
| react-markdown | 10.1.x | Markdown 渲染（引用角标可点击） |

### 3.2 开发依赖

| 包 | 版本 | 作用 |
|----|------|------|
| typescript | 6.0.x | 类型安全（strict: true） |
| vite | 8.0.x | 构建工具（HMR 热重载） |
| @vitejs/plugin-react | 6.0.x | Vite React JSX 支持 |
| vitest | 4.1.x | 单元测试框架 |
| jsdom | 29.1.x | DOM 模拟（测试环境） |
| @testing-library/react | 16.3.x | React 组件测试 |
| @testing-library/jest-dom | 6.9.x | DOM 断言扩展 |
| @testing-library/user-event | 14.6.x | 用户交互模拟 |
| eslint | 10.3.x | JS/TS linter |
| typescript-eslint | 8.59.x | ESLint TypeScript 插件 |
| eslint-plugin-react-hooks | 7.1.x | Hooks 规则检查 |
| eslint-plugin-react-refresh | 0.5.x | HMR 兼容性检查 |
| globals | 17.6.x | ESLint 全局变量配置 |

---

## 4. 其他工具

| 软件 | 版本 | 安装方式 | 作用 |
|------|------|----------|------|
| git | 2.23.x | 系统自带 | 版本控制 |
| Tesseract | 5.5.x | `brew install tesseract` | OCR 引擎（chi_sim 中文语言包） |

---

## 5. 一键安装命令

```bash
# === 容器运行时 ===
brew install colima docker docker-compose
colima start --cpu 4 --memory 8 --disk 60

# === Python 工具链 ===
brew install python@3.14 uv

# === OCR 引擎 ===
brew install tesseract
tesseract --list-langs | grep chi_sim  # 确认中文语言包

# === Node.js ===
brew install node  # Node 26.x

# === 启动基础设施 ===
cd /path/to/PolicyAI
docker compose up -d
docker compose ps

# === 安装各模块依赖 ===
uv sync                    # 根项目（dev 工具）
cd shared && uv sync
cd api-gateway && uv sync
cd services/user-service && uv sync
cd services/llm-router && uv sync
cd services/citation-service && uv sync
cd services/document-service && uv sync
cd services/output-service && uv sync
cd services/kb-service && uv sync
cd services/orchestration-service && uv sync
cd frontend && npm install
```

---

## 6. 质量门禁（每个模块）

```bash
cd <module-directory>
pytest --tb=short           # 所有测试通过
mypy . --strict             # 类型检查（配置 strict 的模块）
ruff check .                # 代码规范
```

---

## 7. 当前环境验证

按 2026-05-21 实际环境：

| 类别 | 软件 | 实际版本 |
|------|------|----------|
| 容器 | Colima + Docker + Compose | 0.10.1 / 29.5.0 / 5.1.3 |
| Python | Python + uv | 3.14.5 / 0.11.9 |
| 测试 | pytest + async + mock | 9.0.3 / 1.3.0 / 3.15.1 |
| 类型 | mypy | 2.1.0 |
| 代码规范 | ruff | 0.15.13 |
| OCR | tesseract + chi_sim | 5.5.2 |
| 版本控制 | git | 2.23.0 |
| 前端 | Node + npm | 26.0.0 / 11.12.1 |
| 前端框架 | React + TypeScript + Vite | 19.2.6 / 6.0.2 / 8.0.12 |
| UI 库 | Ant Design | 6.4.3 |
| 前端测试 | vitest + testing-library | 4.1.6 / 16.3.2 |

全量测试：**638 个测试全部通过**（Python 622 + TypeScript 16）。